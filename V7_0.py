import serial
import time
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QObject, Signal, Slot, QThread, QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
from PySide6 import QtCore, QtWidgets
import traceback
import threading

# Serial port configuration
COM_PORT = "/dev/ttyACM0"  # Replace with your actual COM port
BAUD_RATE = 115200


class Sperctra3Worker(QObject):

    spectra3_ready = Signal(np.ndarray)
    finished = Signal()
    error = Signal(str)


    def __init__(self, ser, ser_lock, in_waiting, data_lock, duration, parent=None):
        super().__init__(parent)
        self.ser = ser
        self.ser_lock = ser_lock
        self.in_waiting = in_waiting
        self.data_lock = data_lock
        self.duration = duration

    @Slot()
    def run(self):
        end_time = time.time() + self.duration
        try:
            while time.time() < end_time:
                with self.ser_lock:
                    command = "3"
                    self.ser.write(command.encode('utf-8'))

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
                        data_array3 = np.array(intensities)
                        with self.data_lock:
                            self.spectra3_ready.emit(data_array3)
                else:
                    time.sleep(0.05)
                        

        except Exception as e:
            self.error.emit(str(e))

        finally:
            self.finished.emit()




class SpectraPlotter(QObject):
    def __init__(self, com_port, baud_rate):
        super().__init__()
        self.com_port = com_port
        self.baud_rate = baud_rate
        self.ser = None
        self.app = pg.mkQApp("Real-time Spectra Plotting")

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
        self.nm = np.linspace(340, 850, 296)  # wavelength range
        self.plot.setLabel('left', 'Intensity')
        self.plot.setLabel('bottom', 'Wavelength (nm)')

        self.plot_widget.nextCol()

        # Infrasarkanais
        self.plotIR = self.plot_widget.addPlot(title="Infrared Spectra")
        self.curveIR = self.plotIR.plot(pen='r')
        self.nmIR = np.linspace(640, 1050, 256)  # wavelength range
        self.plotIR.setLabel('left', 'Intensity')
        self.plotIR.setLabel('bottom', 'Wavelength (nm)')

        
        # Buttons5
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
        self.reading_started = False
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
            self.ser = serial.Serial(self.com_port, self.baud_rate, timeout=0.1)
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
            self.ser.reset_input_buffer()
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
                            value = float(line)
                            intensities.append(value)
                        except ValueError:
                            continue
                    
                    _ = self.ser.readline()
                    
                    intensitiesIR = []
                    for _ in range(256):
                        line = self.ser.readline().decode('utf-8').strip()
                        try:
                            value = float(line)
                            intensitiesIR.append(value)
                        except ValueError:
                            continue

                    spectra_complete = len(intensities) == 296 
                    IRspectra_complete = len(intensitiesIR) == 256  

                    if not spectra_complete and not IRspectra_complete:
                        return (False, False)
                    
                    self.data_array = np.array(intensities)
                    self.data_arrayIR = np.array(intensitiesIR)

                    with self.data_lock:
                        self.spectra_ready = True
                        self.IRspectra_ready = True
                                      
                    return (spectra_complete, IRspectra_complete)
                
                return False, False
                

            except Exception as e:
                print(f"An error occurred during spectrum read: {e}")
                self.running = False 
                return (False, False)
    

    def read_loop(self):
        while self.running:
            if self.reading_started:

                spectra_ready, IRspectra_ready = self.read_spectra()

                if spectra_ready and IRspectra_ready:
                    with self.data_lock:
                        self.latest_spectra = self.data_array.copy()
                        self.latest_spectraIR = self.data_arrayIR.copy()                        
                    self.collected_data.append(self.data_array)
                    self.collected_dataIR.append(self.data_arrayIR)


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
                            value = float(line)
                            intensities.append(value)
                        except ValueError:
                            continue
                    

                    spectra3_complete = len(intensities) == 296 

                    if spectra3_complete:
                        self.data_array3 = np.array(intensities)
                        self.latest_spectra3 = self.data_array3.copy()
                                        
                    return (spectra3_complete)
                
                return (False)

            except Exception as e:
                traceback.print_exc()
                print(f"An error occurred during light spectrum read: {e}")
                return (False)

    

    def update_plot(self):
        if self.reading_started:
            with self.data_lock:
                if self.spectra_ready and self.latest_spectra is not None:
                    self.curve.setData(self.nm, self.latest_spectra)
                    self.spectra_ready = False

                if self.IRspectra_ready and self.latest_spectraIR is not None:
                    self.curveIR.setData(self.nmIR, self.latest_spectraIR)
                    self.IRspectra_ready = False

    
    def instant_measurement(self):
        try:


            self.stop_reading()


            duration = 5

            filename = time.strftime("Spektri_%Y%m%d-%H%M%S.txt") 

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

        self.stop_reading()
        duration = 5
        self.collected_data3 = []
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)

        with self.ser_lock:
            self.ser.reset_input_buffer()
            
        self.worker3 = Sperctra3Worker(self.ser, self.ser_lock, self.ser.in_waiting, self.data_lock, duration)
        self.thread3 = QtCore.QThread(self)
        self.worker3.moveToThread(self.thread3)

        self.thread3.started.connect(self.worker3.run)
        self.worker3.spectra3_ready.connect(self.update_spectra3)
        self.worker3.error.connect(lambda msg: print("3rd spectra error:", msg))
        self.worker3.finished.connect(self.worker3_finsihed)
        self.thread3.finished.connect(self.thread3.quit)

        self.thread3.start()


    def update_spectra3(self, spectrum3: np.ndarray):
        with self.data_lock:
            self.collected_data3.append(spectrum3)

    def worker3_finsihed(self):
        try:
            self.save_spectra3()
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
            self.thread3.quit()



    def save_spectra3(self):
        try: 

            with self.ser_lock:
                self.ser.reset_input_buffer()
                self.ser.flush()


            filename3 = time.strftime("Gaisma_%Y%m%d-%H%M%S.txt") 

            if not self.collected_data3:
                QtWidgets.QMessageBox.warning(
                    self.main_window,
                    "No Data",
                    "No light spectra measured."
                )
                return


            with open(filename3, 'w') as f:
                if self.collected_data3:
                    spectra3_saved = np.array(self.collected_data3).T
                    f.write(" #Falling light Spectra\n")
                    for row in spectra3_saved:
                        f.write(' '.join(map(str, row)) + '\n') 
                
            
                
        except Exception as e:
            traceback.print_exc()
            QtWidgets.QApplication.restoreOverrideCursor()
            print(f"Error saving spectra: {e}")

        finally: 
            QtWidgets.QApplication.restoreOverrideCursor()
            self.start_reading()
        




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
        data_thread = threading.Thread(target=self.read_loop)
        data_thread.daemon = True 
        data_thread.start()

        self.plot_timer = pg.QtCore.QTimer(self)
        self.plot_timer.timeout.connect(self.update_plot)
        self.plot_timer.start(1000)

        self.app.exec() 
        self.running = False
        data_thread.join()
        self.ser.close()

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
