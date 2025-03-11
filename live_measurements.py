import serial
import time
import struct
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtWidgets, QtCore
import traceback
import threading

# Serial port configuration
COM_PORT = "COM5"  # Replace with your actual COM port
BAUD_RATE = 2000000

class SpectraPlotter:
    def __init__(self, com_port, baud_rate):
        self.com_port = com_port
        self.baud_rate = baud_rate
        self.ser = None
        self.app = pg.mkQApp("Real-time Spectra Plotting")
        
        self.main_window = QtWidgets.QMainWindow()
        self.main_window.setWindowTitle("Real-time Spectra")
        self.main_window.resize(800, 600)
        
        central_widget = QtWidgets.QWidget()
        self.main_window.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        
        # Plot
        self.plot_widget = pg.GraphicsLayoutWidget()
        main_layout.addWidget(self.plot_widget)

        self.plot = self.plot_widget.addPlot(title="Spectra")
        self.curve = self.plot.plot(pen='r')
        self.nm = np.linspace(340, 850, 296)  # wavelength range
        self.plot.setLabel('left', 'Intensity')
        self.plot.setLabel('bottom', 'Wavelength (nm)')
        self.plot.setYRange(0, 65000)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        main_layout.addLayout(button_layout)
        
        self.start_button = QtWidgets.QPushButton("Start Reading")
        self.stop_button = QtWidgets.QPushButton("Stop Reading")
        self.save_button = QtWidgets.QPushButton("Measurement")
        self.exposure_button = QtWidgets.QPushButton("Set Exposure")
        
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.exposure_button)

        self.start_button.clicked.connect(self.start_reading)
        self.stop_button.clicked.connect(self.stop_reading)
        self.save_button.clicked.connect(self.save_spectra)
        self.exposure_button.clicked.connect(self.set_exposure)

        # Initialization
        self.data_array = np.zeros(296)
        self.running = False
        self.reading_started = False
        self.colleted_data = []
        self.ser_lock = threading.Lock()
        self.data_lock = threading.Lock()
        self.latest_spectrum = None
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
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)


    def stop_reading(self):
        if self.ser and self.reading_started:
            self.reading_started = False 
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)


    def set_exposure(self):

        self.reading_started = False
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)


        if not self.ser:
            QtWidgets.QMessageBox.warning(self.main_window, "Serial Port Error", "Serial port not connected.")
            return

        self.stop_reading()
        self.exposure_adjusting = True

        try:
            with self.ser_lock:
                self.ser.write('1'.encode('utf-8'))
            time.sleep(0.05)
            response = self.ser.readline().decode('utf-8').strip()

            # Open a dialog to enter an exposure value
            if response is not None:
                text, ok = QtWidgets.QInputDialog.getText(self.main_window, "Set Exposure", "Enter exposure value (or type 'auto' for automatic):")
                if ok:
                    if text.lower() == "auto":
                        command = "auto"
                    else:
                        try:
                            value = float(text)
                            command = f"{value}"
                        except ValueError:
                            QtWidgets.QMessageBox.warning(self.main_window, "Invalid Input", "Please enter a numeric value of 1-2000")
                            self.exposure_adjusting = False
                            return

                    with self.ser_lock:
                        self.ser.write(command.encode('utf-8'))
                    time.sleep(9.5)
                    with self.ser_lock:
                        self.ser.reset_input_buffer()
                    self.exposure_adjusting = False

        except Exception as e:
            traceback.print_exc()
            print(f"An error occurred in set_exposure: {e}")



    def read_spectra(self):
        start_command = "2"
        self.ser.write(start_command.encode('utf-8'))  
        time.sleep(0.01)
        try:
            if self.ser.in_waiting:

                # Discard text line
                _ = self.ser.readline()
                
                # Read intesities
                intensities = []
                for _ in range(296):
                    line = self.ser.readline().decode('utf-8').strip()
                    try:
                        value = float(line)
                        intensities.append(value)
                    except ValueError:
                        continue
                
                if len(intensities) == 296:
                    self.data_array = np.array(intensities)
                    return self.data_array
            return None


        except serial.SerialException as e:
            print(f"Serial port error during spectrum read: {e}")
            self.running = False 
            return None
        except struct.error as e:
            print(f"Unpacking error: {e}")
            return None
        except Exception as e:
            print(f"An error occurred during spectrum read: {e}")
            self.running = False 
            return None

    def read_loop(self):
        # Background thread loop for reading spectra continuously
        while self.running:
            if self.reading_started:
                spectrum = self.read_spectra()
                if spectrum is not None:
                    with self.data_lock:
                        self.latest_spectrum = spectrum
                    self.colleted_data.append(spectrum)


    def update_plot(self):
        # Called periodically by QTimer to update plot
        if self.reading_started:
            with self.data_lock:
                if self.latest_spectrum is not None:
                    self.curve.setData(self.nm, self.latest_spectrum)

    def save_spectra(self):
        try:
            # Ask user for the number of measurements
            count, ok = QtWidgets.QInputDialog.getInt(
                self.main_window,
                "Number of measurements",
                "Enter number of spectra measurements:",
                value=1,
                min=1,
                max=100000
            )
            if not ok:
                return

            # Ask user where to save the file
            filename, _ = QtWidgets.QFileDialog.getSaveFileName(
                self.main_window,
                "Save measurement",
                "",
                "Text Files (*.txt)"
            )
            if not filename:
                return

            measurements = []

            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            for i in range(count):
                spectrum = self.read_spectra()
                if spectrum is not None:
                    measurements.append(spectrum)
                #time.sleep(0.001)  # Adjust delay if needed

            with open(filename, 'w') as f:
                for spectrum in measurements:
                    if spectrum is not None:
                        f.write(','.join(map(str, spectrum)) + '\n')
                        f.write('---\n') 

            QtWidgets.QApplication.restoreOverrideCursor()

        except Exception as e:
            QtWidgets.QApplication.restoreOverrideCursor()
            traceback.print_exc()
            print(f"Error saving spectra: {e}")

    def run(self):
        if not self.connect_serial():
            return
        self.running = True 
        # Start the robust reading thread that continuously polls the serial port.
        data_thread = threading.Thread(target=self.read_loop)
        data_thread.daemon = True 
        data_thread.start()

        timer = pg.QtCore.QTimer()
        timer.timeout.connect(self.update_plot)
        timer.start(500)

        self.app.exec() 
        self.running = False 
        data_thread.join() 
        self.ser.close()


if __name__ == "__main__":
    plotter = SpectraPlotter(COM_PORT, BAUD_RATE)
    plotter.run()