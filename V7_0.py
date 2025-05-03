import serial
import time
import struct
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtWidgets, QtCore
import traceback
import threading
import queue

COM_PORT = "/dev/ttyACM0" 
BAUD_RATE = 115200

class SpectraPlotter:
    def __init__(self, com_port, baud_rate):
        self.com_port = com_port
        self.baud_rate = baud_rate
        self.ser = None
        self.app = pg.mkQApp("Real-time Spectra")

        pg.setConfigOption('background', 'w')
        
        self.main_window = QtWidgets.QMainWindow()
        self.main_window.setWindowTitle("Real-time Spectra")
        self.main_window.resize(800, 480)
        central_widget = QtWidgets.QWidget()
        self.main_window.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        
        # Plot
        self.plot_widget = pg.GraphicsLayoutWidget()
        main_layout.addWidget(self.plot_widget)

        self.plot = self.plot_widget.addPlot(title="Visible Spectra")
        self.curve = self.plot.plot(pen='#0000FF')
        self.nm = np.linspace(340, 850, 296) 
        self.plot.setLabel('left', 'Intensity')
        self.plot.setLabel('bottom', 'Wavelength (nm)')

        self.plot_widget.nextCol()

        # Infrasarkanais
        self.plotIR = self.plot_widget.addPlot(title="Infrared Spectra")
        self.curveIR = self.plotIR.plot(pen='r')
        self.nmIR = np.linspace(640, 1050, 256) 
        self.plotIR.setLabel('left', 'Intensity')
        self.plotIR.setLabel('bottom', 'Wavelength (nm)')
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        main_layout.addLayout(button_layout)
        
        self.instant_button = QtWidgets.QPushButton("Measurement")
        self.instant3_button = QtWidgets.QPushButton("3rd Spectra")
        
        button_layout.addWidget(self.instant_button)
        button_layout.addWidget(self.instant3_button)

        self.instant_button.clicked.connect(self.instant_measurement)
        self.instant3_button.clicked.connect(self.instant_measurement3)

        # Initialization
        self.data_array = np.zeros(296)
        self.data_arrayIR = np.zeros(256)
        self.data_array3 = np.zeros(296)
        self.running = False
        self.running3 = False
        self.reading_started = False
        self.reading_started3 = False
        self.collected_data = []
        self.collected_dataIR = []
        self.collected_data3 = []
        self.ser_lock = threading.Lock()
        self.data_lock = threading.Lock()
        self.latest_spectra = None
        self.latest_spectraIR = None
        self.latest_spectra3 = None

        self.spectra_ready = False
        self.IRspectra_ready = False
        self.spectra3_ready = False

        self.main_window.show()

    def connect_serial(self):
        try:
            self.ser = serial.Serial(self.com_port, self.baud_rate, timeout=0.5)
            return True
        except serial.SerialException as e:
            print(f"Error opening serial port: {e}")
            return False
        
    def start_reading(self):
        self.reading_started = True


    def stop_reading(self):
        self.reading_started = False


    def read_spectra(self):
        with self.ser_lock:
            start_command = "5"
            self.ser.write(start_command.encode('utf-8'))  

            try:
                
                if self.ser.in_waiting:
                    _ = self.ser.readline()
                    _ = self.ser.readline()
                    

                    intensities = []
                    for _ in range(296):
                        line = self.ser.readline().decode('utf-8').strip()
                        try:
                            value = int(line)
                            intensities.append(value)
                        except ValueError:
                            continue
                    
                    _ = self.ser.readline()
                    
                    intensitiesIR = []
                    for _ in range(256):
                        line = self.ser.readline().decode('utf-8').strip()
                        try:
                            value = int(line)
                            intensitiesIR.append(value)
                        except ValueError:
                            continue
                    
                    spectra_complete = len(intensities) == 296 
                    IRspectra_complete = len(intensitiesIR) == 256

                    if spectra_complete and IRspectra_complete:
                        self.data_array = np.array(intensities)
                        self.data_arrayIR = np.array(intensitiesIR)
                        self.spectra_ready = True
                        self.IRspectra_ready = True
                        
                        self.latest_spectra = self.data_array.copy()
                        self.latest_spectraIR = self.data_arrayIR.copy()

                
            except Exception as e:
                print(f"An error occurred during spectrum read: {e}")
                traceback.print_exc()
                return None

    def read_loop(self):
        while self.running:
            if self.reading_started:
                self.read_spectra()
                
                if self.spectra_ready and self.IRspectra_ready:
                    with self.data_lock:
                        self.collected_data.append(self.latest_spectra.copy())
                        self.collected_dataIR.append(self.latest_spectraIR.copy())
                    
                    self.spectra_ready = False
                    self.IRspectra_ready = False
                
            else:
                time.sleep(0.05)

    def read_spectra3(self):
        with self.ser_lock:
            start_command = "3"
            self.ser.write(start_command.encode('utf-8'))  

            try:
                
                if self.ser.in_waiting:
                    _ = self.ser.readline()
                    
                    intensities = []
                    for _ in range(296):
                        line = self.ser.readline().decode('utf-8').strip()
                        try:
                            value = int(line)
                            intensities.append(value)
                        except ValueError:
                            continue
                    
                    spectra3_complete = len(intensities) == 296 

                    if spectra3_complete:
                        self.data_array3 = np.array(intensities)
                        self.latest_spectra3 = self.data_array3.copy()
                        self.collected_data3.append(self.data_array3)
                
            except Exception as e:
                print(f"An error occurred during light spectrum read: {e}")
                traceback.print_exc()
                return None
    
    def read_loop3(self):
        while self.running3:
            if self.reading_started3:
                self.read_spectra3()
            else:
                time.sleep(0.05)

    def update_plot(self):
        try:
            if self.latest_spectra is not None:
                self.curve.setData(self.nm, self.latest_spectra)

            if self.latest_spectraIR is not None:
                self.curveIR.setData(self.nmIR, self.latest_spectraIR)
                
        except Exception as e:
            print(f"Error updating plot: {e}")
            traceback.print_exc()
    
    def instant_measurement(self):
        try:
            self.stop_reading()
            duration = 5
            filename = time.strftime("Spektri_%Y%m%d-%H%M%S.txt") 

            with self.data_lock:
                self.collected_data = []
                self.collected_dataIR = []

            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)

            with self.ser_lock:
                self.ser.reset_input_buffer()

            self.start_reading()
            start_time = time.time()   

            while (time.time() - start_time) < duration:
                QtWidgets.QApplication.processEvents() 
                time.sleep(0.05) 
                
            self.stop_reading()

            if not self.collected_data and not self.collected_dataIR:
                QtWidgets.QApplication.restoreOverrideCursor()
                QtWidgets.QMessageBox.warning(
                    self.main_window,
                    "No Data",
                    "No spectra measured."
                )
                return

            with open(filename, 'w') as f:
                if self.collected_data:
                    spectra_saved = np.array(self.collected_data).T
                    f.write(" #Visible Spectra\n")
                    for row in spectra_saved:
                        f.write(' '.join(map(str, row)) + '\n') 
                
                if self.collected_dataIR:
                    spectra_savedIR = np.array(self.collected_dataIR).T
                    f.write(" #Infrared Spectra\n")
                    for row in spectra_savedIR:
                        f.write(' '.join(map(str, row)) + '\n')

            QtWidgets.QApplication.restoreOverrideCursor()

            time.sleep(0.5)
            self.start_reading()
                
        except Exception as e:
            QtWidgets.QApplication.restoreOverrideCursor()
            traceback.print_exc()
            print(f"Error saving spectra: {e}")

    def instant_measurement3(self):
        try:
            self.reading_started = False
            duration = 3
            filename = time.strftime("Gaisma_%Y%m%d-%H%M%S.txt") 

            self.collected_data3 = []

            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)

            with self.ser_lock:
                self.ser.reset_input_buffer()
                
            self.reading_started3 = True
            
            start_time = time.time()   

            while (time.time() - start_time) < duration:
                QtWidgets.QApplication.processEvents() 
                time.sleep(0.05) 
            
            self.reading_started3 = False

            time.sleep(0.05)

            with self.ser_lock:
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()

            if not self.collected_data3:
                QtWidgets.QApplication.restoreOverrideCursor()
                QtWidgets.QMessageBox.warning(
                    self.main_window,
                    "No Data",
                    "No light spectra measured."
                )
                return

            with open(filename, 'w') as f:
                if self.collected_data3:
                    spectra3_saved = np.array(self.collected_data3).T
                    f.write(" #Falling light Spectra\n")
                    for row in spectra3_saved:
                        f.write(' '.join(map(str, row)) + '\n') 
            
            self.reading_started = True           
            QtWidgets.QApplication.restoreOverrideCursor()
                
        except Exception as e:
            QtWidgets.QApplication.restoreOverrideCursor()
            traceback.print_exc()
            print(f"Error saving falling spectra: {e}")

    def run(self):
        if not self.connect_serial():
            QtWidgets.QMessageBox.warning(
                self.main_window,
                "Serial Port Error",
                "Serial port not connected."
            )
            return
        
        self.running = True 
        self.reading_started = True
        self.running3 = True
        self.reading_started3 = False
        

        data_thread = threading.Thread(target=self.read_loop)
        data3_thread = threading.Thread(target=self.read_loop3)
        data_thread.daemon = True 
        data3_thread.daemon = True
        data_thread.start()
        data3_thread.start()

        timer = pg.QtCore.QTimer()
        timer.timeout.connect(self.update_plot)
        timer.start(1000)  

        self.app.exec() 
        self.running = False
        self.running3 = False 
        data_thread.join(timeout=1.0)
        data3_thread.join(timeout=1.0)
        
        if self.ser and self.ser.is_open:
            self.ser.close()

        exit_app = QtWidgets.QApplication([])
        msg_box = QtWidgets.QMessageBox()
        msg_box.setWindowTitle("Application Finished")
        msg_box.setText("Click OK to exit.")
        msg_box.exec()

if __name__ == "__main__":
    plotter = SpectraPlotter(COM_PORT, BAUD_RATE)
    plotter.run()
