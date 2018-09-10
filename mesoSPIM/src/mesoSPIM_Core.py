'''
Core for the mesoSPIM project
=============================
'''
import os
import numpy as np
import time
from scipy import signal
import csv
import traceback

'''PyQt5 Imports'''
from PyQt5 import QtWidgets, QtCore, QtGui

'''National Instruments Imports'''
# import nidaqmx
# from nidaqmx.constants import AcquisitionType, TaskMode
# from nidaqmx.constants import LineGrouping, DigitalWidthUnits
# from nidaqmx.types import CtrTime

''' Import mesoSPIM modules '''
from .mesoSPIM_State import mesoSPIM_StateSingleton
from .devices.shutters.NI_Shutter import NI_Shutter
from .mesoSPIM_Camera import mesoSPIM_HamamatsuCamera
from .devices.lasers.mesoSPIM_LaserEnabler import mesoSPIM_LaserEnabler
from .mesoSPIM_Serial import mesoSPIM_Serial
from .mesoSPIM_WaveFormGenerator import mesoSPIM_WaveFormGenerator

from .utils.acquisitions import AcquisitionList, Acquisition

class mesoSPIM_Core(QtCore.QObject):
    '''This class is the pacemaker of a mesoSPIM

    Signals it can send:

    '''

    sig_finished = QtCore.pyqtSignal()

    sig_update_gui_from_state = QtCore.pyqtSignal(bool)

    sig_state_request = QtCore.pyqtSignal(dict)
    sig_state_request_and_wait_until_done = QtCore.pyqtSignal(dict)
    sig_position = QtCore.pyqtSignal(dict)
    
    sig_progress = QtCore.pyqtSignal(dict)

    ''' Camera-related signals '''
    sig_prepare_image_series = QtCore.pyqtSignal(Acquisition)
    sig_add_images_to_image_series = QtCore.pyqtSignal()
    sig_end_image_series = QtCore.pyqtSignal()

    ''' Movement-related signals: '''
    sig_move_relative = QtCore.pyqtSignal(dict)
    sig_move_relative_and_wait_until_done = QtCore.pyqtSignal(dict)
    sig_move_absolute = QtCore.pyqtSignal(dict)
    sig_move_absolute_and_wait_until_done = QtCore.pyqtSignal(dict)
    sig_zero_axes = QtCore.pyqtSignal(list)
    sig_unzero_axes = QtCore.pyqtSignal(list)
    sig_stop_movement = QtCore.pyqtSignal()
    sig_load_sample = QtCore.pyqtSignal()
    sig_unload_sample = QtCore.pyqtSignal()

    ''' ETL-related signals '''
    sig_save_etl_config = QtCore.pyqtSignal()

    def __init__(self, config, parent):
        super().__init__()

        ''' Assign the parent class to a instance variable for callbacks '''
        self.parent = parent
        self.cfg = self.parent.cfg

        self.state = mesoSPIM_StateSingleton()
        self.state['state']='init'

        ''' The signal-slot switchboard '''
        self.parent.sig_state_request.connect(self.state_request_handler)

        self.parent.sig_execute_script.connect(self.execute_script)

        self.parent.sig_move_relative.connect(lambda dict: self.move_relative(dict))
        self.parent.sig_move_relative_and_wait_until_done.connect(lambda dict: self.move_relative(dict, wait_until_done=True))
        self.parent.sig_move_absolute.connect(lambda dict: self.move_absolute(dict))
        self.parent.sig_move_absolute_and_wait_until_done.connect(lambda dict: self.move_absolute(dict, wait_until_done=True))
        self.parent.sig_zero_axes.connect(lambda list: self.zero_axes(list))
        self.parent.sig_unzero_axes.connect(lambda list: self.unzero_axes(list))
        self.parent.sig_stop_movement.connect(self.stop_movement)
        self.parent.sig_load_sample.connect(self.sig_load_sample.emit)
        self.parent.sig_unload_sample.connect(self.sig_unload_sample.emit)
        self.parent.sig_save_etl_config.connect(self.sig_save_etl_config.emit)

        ''' Set the Camera thread up '''
        self.camera_thread = QtCore.QThread()
        self.camera_worker = mesoSPIM_HamamatsuCamera(self)
        self.camera_worker.moveToThread(self.camera_thread)

        ''' Set the serial thread up '''
        self.serial_thread = QtCore.QThread()
        self.serial_worker = mesoSPIM_Serial(self)
        self.serial_worker.moveToThread(self.serial_thread)
        self.serial_worker.sig_position.connect(lambda dict: self.sig_position.emit(dict))

        ''' Start the threads '''
        self.camera_thread.start()
        self.serial_thread.start()

        ''' Setting waveform generation up '''
        self.waveformer = mesoSPIM_WaveFormGenerator(self)
        self.waveformer.sig_update_gui_from_state.connect(lambda flag: self.sig_update_gui_from_state.emit(flag))
        self.sig_state_request.connect(self.waveformer.state_request_handler)
        self.sig_state_request_and_wait_until_done.connect(self.waveformer.state_request_handler, type=3)

        ''' Setting the shutters up '''
        left_shutter_line = self.cfg.shutterdict['shutter_left']
        right_shutter_line = self.cfg.shutterdict['shutter_right']

        self.shutter_left = NI_Shutter(left_shutter_line)
        self.shutter_right = NI_Shutter(right_shutter_line)

        self.shutter_left.close()
        self.shutter_right.close()
        self.state['shutterstate'] = False

        ''' Setting the laserenabler up '''
        self.laserenabler = mesoSPIM_LaserEnabler(self.cfg.laserdict)

        self.state['state']='idle'

        self.stopflag = False

    def __del__(self):
        '''Cleans the threads up after deletion, waits until the threads
        have truly finished their life.

        Make sure to keep this up to date with the number of threads
        '''
        try:
            self.camera_thread.quit()
            self.serial_thread.quit()

            self.camera_thread.wait()
            self.serial_thread.wait()
        except:
            pass


    @QtCore.pyqtSlot(dict)
    def state_request_handler(self, dict):
        for key, value in zip(dict.keys(),dict.values()):
            print('Core Thread: State request: Key: ', key, ' Value: ', value)
            '''
            The request handling is done with exec() to write fewer lines of
            code.
            '''
            if key in ('filter',
                       'zoom',
                       'laser',
                       'intensity',
                       'shutterconfig',
                       'state',
                       'camera_exposure_time',
                       'camera_line_interval'):
                exec('self.set_'+key+'(value)')

            elif key in ('samplerate',
                       'sweeptime',
                       'ETL_cfg_file',
                       'etl_l_delay_%',
                       'etl_l_ramp_rising_%',
                       'etl_l_ramp_falling_%',
                       'etl_l_amplitude',
                       'etl_l_offset',
                       'etl_r_delay_%',
                       'etl_r_ramp_rising_%',
                       'etl_r_ramp_falling_%',
                       'etl_r_amplitude',
                       'etl_r_offset',
                       'galvo_l_frequency',
                       'galvo_l_amplitude',
                       'galvo_l_offset',
                       'galvo_l_duty_cycle',
                       'galvo_l_phase',
                       'galvo_r_frequency',
                       'galvo_r_amplitude',
                       'galvo_r_offset',
                       'galvo_r_duty_cycle',
                       'galvo_r_phase',
                       'laser_l_delay_%',
                       'laser_l_pulse_%',
                       'laser_l_max_amplitude',
                       'laser_r_delay_%',
                       'laser_r_pulse_%',
                       'laser_r_max_amplitude',
                       'camera_delay_%',
                       'camera_pulse_%'):
                self.sig_state_request.emit({key : value})
            
    def set_state(self, state):
        if state == 'live':
            self.state['state']='live'
            self.sig_state_request.emit({'state':'live'})
            self.live()
        
        elif state == 'run_selected_acquisition':
            self.state['state']= 'run_selected_acquisition'
            self.sig_state_request.emit({'state':'run_selected_acquisition'})
            self.start(row = self.state['selected_row'])

        elif state == 'run_acquisition_list':
            self.state['state'] = 'run_acquisition_list'
            self.sig_state_request.emit({'state':'run_acquisition_list'})
            self.start(row = None)

        elif state == 'idle':
            print('Core: Stopping requested')
            self.sig_state_request.emit({'state':'idle'})
            self.stop()

        elif state == 'lightsheet_alignment_mode':
            self.state['state'] = 'lightsheet_alignment_mode'
            self.sig_state_request.emit({'state':'live'})
            self.lightsheet_alignment_mode()

        elif state == 'visual_mode':
            self.state['state'] = 'visual_mode'
            self.sig_state_request.emit({'state':'live'})
            self.visual_mode()

    def stop(self):
        self.stopflag = True
        ''' This stopflag is a bit risky, needs to be updated'''
        self.state['state']='idle'
        self.sig_update_gui_from_state.emit(False)
        self.sig_finished.emit()

    def send_progress(self,
                      cur_acq,
                      tot_acqs,
                      cur_image,
                      images_in_acq,
                      total_image_count,
                      image_counter):

        dict = {'current_acq':cur_acq,
                'total_acqs' :tot_acqs,
                'current_image_in_acq':cur_image,
                'images_in_acq': images_in_acq,
                'total_image_count':total_image_count,
                'image_counter':image_counter,
        }
        self.sig_progress.emit(dict)

    def set_filter(self, filter, wait_until_done=False):
        if wait_until_done:
            self.sig_state_request_and_wait_until_done.emit({'filter' : filter})
        else:
            self.sig_state_request.emit({'filter' : filter})

    def set_zoom(self, zoom, wait_until_done=False):
        if wait_until_done:
            self.sig_state_request_and_wait_until_done.emit({'zoom' : zoom})
        else:
            self.sig_state_request.emit({'zoom' : zoom})

    def set_laser(self, laser, wait_until_done=False):
        self.laserenabler.enable(laser)
        if wait_until_done:
            self.sig_state_request_and_wait_until_done.emit({'laser' : laser})
        else: 
            self.sig_state_request.emit({'laser':laser})

    def set_intensity(self, intensity, wait_until_done=False):
        if wait_until_done:
            self.sig_state_request_and_wait_until_done.emit({'intensity': intensity})
        else:
            self.sig_state_request.emit({'intensity':intensity})

    def set_camera_exposure_time(self, time):
        self.sig_state_request.emit({'camera_exposure_time' : time})

    def set_camera_line_interval(self, time):
        self.sig_state_request.emit({'camera_line_interval' : time})

    def move_relative(self, dict, wait_until_done=False):
        if wait_until_done:
            self.sig_move_relative_and_wait_until_done.emit(dict)
        else:
            self.sig_move_relative.emit(dict)

    def move_absolute(self, dict, wait_until_done=False):
        if wait_until_done:
            self.sig_move_absolute_and_wait_until_done.emit(dict)
        else:
            self.sig_move_absolute.emit(dict)

    def zero_axes(self, list):
        self.sig_zero_axes.emit(list)

    def unzero_axes(self, list):
        self.sig_unzero_axes.emit(list)

    def stop_movement(self):
        self.sig_stop_movement.emit()

    def set_shutterconfig(self, shutterconfig):
        self.state['shutterconfig'] = shutterconfig

    def open_shutters(self):
        shutterconfig = self.state['shutterconfig']

        if shutterconfig == 'Both':
            self.shutter_left.open()
            self.shutter_right.open()
        elif shutterconfig == 'Left':
            self.shutter_left.open()
            self.shutter_right.close()
        elif shutterconfig == 'Right':
            self.shutter_right.open()
            self.shutter_left.close()
        else:
            self.shutter_right.open()
            self.shutter_left.open()

        self.state['shutterstate'] = True
   
    def close_shutters(self):
        self.shutter_left.close()
        self.shutter_right.close()
        self.state['shutterstate'] = False

    '''
    Sub-Imaging modes
    '''
    def snap(self):
        self.open_shutters()
        self.snap_image()
        self.close_shutters()
        self.sig_finished.emit()

    def snap_image(self):
        '''Snaps a single image after updating the waveforms.

        Can be used in acquisitions where changing waveforms are required,
        but there is additional overhead due to the need to write the
        waveforms into the buffers of the NI cards.
        '''

        self.waveformer.create_tasks()
        self.waveformer.write_waveforms_to_tasks()
        self.waveformer.start_tasks()
        self.waveformer.run_tasks()
        self.waveformer.stop_tasks()
        self.waveformer.close_tasks()

    def prepare_image_series(self):
        '''Prepares an image series without waveform update'''
        self.waveformer.create_tasks()
        self.waveformer.write_waveforms_to_tasks()

    def snap_image_in_series(self):
        '''Snaps and image from a series without waveform update'''
        self.waveformer.start_tasks()
        self.waveformer.run_tasks()
        self.waveformer.stop_tasks()

    def close_image_series(self):
        '''Cleans up after series without waveform update'''
        self.waveformer.close_tasks()

    '''
    Execution code for major imaging modes starts here
    '''
        
    def live(self):
        self.stopflag = False

        self.open_shutters()
        while self.stopflag is False:
            ''' Needs update to use snap image in series '''
            self.snap_image()

            QtWidgets.QApplication.processEvents()

            ''' How to handle a possible shutter switch?'''
            self.open_shutters()

        self.close_shutters()

        self.sig_finished.emit()

    def start(self, row=None):
        self.stopflag = False

        if row==None:
            acq_list = self.state['acq_list']
        else:
            acquisition = self.state['acq_list'][row]
            acq_list = AcquisitionList([acquisition])

        if acq_list.has_rotation() == True:
             print('Attention: Has rotation!')
        
        self.sig_update_gui_from_state.emit(True)
        self.prepare_acquisition_list(acq_list)
        self.run_acquisition_list(acq_list)
        self.close_acquisition_list(acq_list)
        self.sig_update_gui_from_state.emit(False)

    def prepare_acquisition_list(self, acq_list):
        '''
        Housekeeping: Prepare the acquisition list
        '''
        self.image_count = 0
        self.acquisition_count = 0
        self.total_acquisition_count = len(acq_list)
        self.total_image_count = acq_list.get_image_count()

    def run_acquisition_list(self, acq_list):
        for acq in acq_list:
            name = acq['filename']
            _time = int(acq.get_acquisition_time())
            filter = acq['filter']
            total_steps = acq.get_image_count()

            displaystring = "Running acquisition with name: " + name + " for " + str(_time) + " seconds and filter:" + filter

            # self.statusMessage.emit(displaystring)

            self.prepare_acquisition(acq)
            self.run_acquisition(acq)
            self.close_acquisition(acq)

    def close_acquisition_list(self, acq_list):
        if not self.stopflag:
            self.move_absolute(acq_list.get_startpoint())
        self.sig_finished.emit()
        
    def prepare_acquisition(self, acq):
        '''
        Housekeeping: Prepare the acquisition
        '''
        print('Running Acquisition #', self.acquisition_count,
                ' with Filename: ', acq['filename'])
        self.move_absolute(acq.get_startpoint(), wait_until_done=True)
        self.set_shutterconfig(acq['shutter'])
        self.set_filter(acq['filter'], wait_until_done=True)
        self.set_zoom(acq['zoom'], wait_until_done=True)
        self.set_laser(acq['laser'], wait_until_done=True)
        self.set_intensity(acq['intensity'], wait_until_done=True)
        self.sig_prepare_image_series.emit(acq)
        self.prepare_image_series()
        self.write_metadata(acq)
        
    def run_acquisition(self, acq):
        steps = acq.get_image_count()

        self.open_shutters()
        for i in range(steps):
            if self.stopflag is True:
                self.close_image_series()
                self.sig_end_image_series.emit()
                break
            self.image_count += 1

            self.snap_image_in_series()
            self.sig_add_images_to_image_series.emit()
            QtWidgets.QApplication.processEvents()
            self.move_relative(acq.get_delta_z_dict(), wait_until_done=True)
            

            self.send_progress(self.acquisition_count,
                               self.total_acquisition_count,
                               i,
                               steps,
                               self.total_image_count,
                               self.image_count)
        self.close_shutters()
        

    def close_acquisition(self, acq):
        if self.stopflag is not True:
            self.move_absolute(acq.get_startpoint(), wait_until_done=True)
            self.close_image_series()
        self.sig_end_image_series.emit()
        self.acquisition_count += 1
  
    @QtCore.pyqtSlot(str)
    def execute_script(self, script):
        self.sig_update_gui_from_state.emit(True)
        self.state['state']='running_script'
        try:
            exec(script)
        except:
            traceback.print_exc()
        self.sig_finished.emit()
        self.state['state']='idle'
        self.sig_update_gui_from_state.emit(False)

    def lightsheet_alignment_mode(self):
        '''Switches shutters after each image to allow coalignment of both lightsheets'''
        self.stopflag = False
        '''Needs more careful adjustment of the timing

        TODO: There is no wait period to wait for the shutters to open. Nonetheless, the
        visual of the mode impression is not too bad.
        '''
        while self.stopflag is False:
            self.shutter_left.open()
            self.snap_image()
            self.shutter_left.close()
            self.shutter_right.open()
            self.snap_image()
            self.shutter_right.close()
            QApplication.processEvents()

        self.close_shutters()
        self.sig_finished.emit()

    def visual_mode(self):
        old_l_amp = self.state['etl_l_amplitude']
        old_r_amp = self.state['etl_r_amplitude']
        self.sig_state_request.emit({'etl_l_amplitude' : 0})
        self.sig_state_request.emit({'etl_r_amplitude' : 0})

        self.prepare_image_series()

        self.stopflag = False

        self.open_shutters()
        while self.stopflag is False:
            ''' Needs update to use snap image in series '''
            self.snap_image_in_series()

            QtWidgets.QApplication.processEvents()

            ''' How to handle a possible shutter switch?'''
            self.open_shutters()

        self.close_image_series()
        self.close_shutters()

        self.sig_finished.emit()

        self.sig_state_request.emit({'etl_l_amplitude' : old_l_amp})
        self.sig_state_request.emit({'etl_r_amplitude' : old_r_amp})

    def write_line(self, file, key='', value=''):
        ''' Little helper method to write a single line with a key and value for metadata

        Adds a line break at the end.
        '''
        if key !='':
            file.write('['+str(key)+'] '+str(value) + '\n')
        else:
            file.write('\n')

    def write_metadata(self, acq):
        '''
        Writes a metadata.txt file

        Path contains the file to be written
        '''
        path = acq['folder']+acq['filename']

        metadata_path = os.path.dirname(path)+'/'+os.path.basename(path)+'_meta.txt'

        print('Metadata_path: ', metadata_path)

        with open(metadata_path,'w') as file:
            self.write_line(file, 'Metadata for file', path)
            self.write_line(file, 'z_stepsize', acq['z_step'])
            self.write_line(file)
            # self.write_line(file, 'COMMENTS')
            # self.write_line(file, 'Comment: ', acq(['comment']))
            # self.write_line(file)
            self.write_line(file, 'CFG')
            self.write_line(file, 'Laser', acq['laser'])
            self.write_line(file, 'Intensity (%)', acq['intensity'])
            self.write_line(file, 'Zoom', acq['zoom'])
            self.write_line(file, 'Pixelsize in um', self.state['pixelsize'])
            self.write_line(file, 'Filter', acq['filter'])
            self.write_line(file, 'Shutter', acq['shutter'])
            self.write_line(file)
            self.write_line(file, 'POSTION')
            self.write_line(file, 'x_pos', acq['x_pos'])
            self.write_line(file, 'y_pos', acq['y_pos'])
            self.write_line(file, 'f_pos', acq['f_pos'])
            self.write_line(file, 'z_start', acq['z_start'])
            self.write_line(file, 'z_end', acq['z_end'])
            self.write_line(file, 'z_stepsize', acq['z_step'])
            self.write_line(file, 'z_planes', acq.get_image_count())
            self.write_line(file)

            ''' Attention: change to true ETL values ASAP '''
            self.write_line(file,'ETL PARAMETERS')
            self.write_line(file, 'ETL CFG File', self.state['ETL_cfg_file'])
            self.write_line(file,'etl_l_offset', self.state['etl_l_offset'])
            self.write_line(file,'etl_l_amplitude', self.state['etl_l_amplitude'])
            self.write_line(file,'etl_r_offset', self.state['etl_r_offset'])
            self.write_line(file,'etl_r_amplitude', self.state['etl_r_amplitude'])
            self.write_line(file)
            self.write_line(file, 'GALVO PARAMETERS')
            self.write_line(file, 'galvo_l_frequency',self.state['galvo_l_frequency'])
            self.write_line(file, 'galvo_l_amplitude',self.state['galvo_l_amplitude'])
            self.write_line(file, 'galvo_l_offset', self.state['galvo_l_offset'])
            self.write_line(file, 'galvo_r_amplitude', self.state['galvo_r_amplitude'])
            self.write_line(file, 'galvo_r_offset', self.state['galvo_r_offset'])
            self.write_line(file)
            self.write_line(file, 'CAMERA PARAMETERS')
            self.write_line(file, 'camera_exposure', self.state['camera_exposure_time'])
            self.write_line(file, 'camera_line_interval', self.state['camera_line_interval'])
