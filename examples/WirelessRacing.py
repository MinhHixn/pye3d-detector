import cv2
import win32gui
import win32con
import threading
import argparse
import numpy as np
import keyboard
import time
from pupil_detectors.detector_2d import Detector2D
from pye3d.detector_3d import CameraModel, Detector3D, DetectorMode
import joblib

class SharedGazeData:
    def __init__(self):
        self.gaze_point = None
        self.lock = threading.Lock()

    def update(self, gaze_point):
        with self.lock:
            self.gaze_point = gaze_point

    def get(self):
        with self.lock:
            return self.gaze_point

class CamThread(threading.Thread):
    def __init__(self, preview_name, stream_url, resolution, is_eye_cam=False, focal_length=None, shared_gaze_data=None, camera_matrix=None, dist_coeffs=None, lr_model=None):
        threading.Thread.__init__(self)
        self.preview_name = preview_name
        self.stream_url = stream_url
        self.resolution = resolution
        self.is_eye_cam = is_eye_cam
        self.shared_gaze_data = shared_gaze_data
        self.running = True
        self.debug_info = ""
        self.camera_matrix = camera_matrix
        self.dist_coeffs = dist_coeffs
        self.lr_model = lr_model
        self.w_pressed = False

        if is_eye_cam:
            self.detector_2d = Detector2D()
            self.camera = CameraModel(focal_length=focal_length, resolution=resolution)
            self.detector_3d = Detector3D(camera=self.camera, long_term_mode=DetectorMode.blocking)

    def run(self):
        print(f'Starting {self.preview_name}')
        self.cam_preview()

    def stop(self):
        self.running = False
        if self.w_pressed:
            keyboard.release('w')

    def process_eye_frame(self, frame, frame_number):
        grayscale = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        result_2d = self.detector_2d.detect(grayscale)
        result_2d["timestamp"] = frame_number
        result_3d = self.detector_3d.update_and_detect(result_2d, grayscale)
        
        if result_3d['confidence'] < 0.6:
            keyboard.press('w')
            self.w_pressed = True
        else:
            if self.w_pressed:
                keyboard.release('w')
                self.w_pressed = False
        
        if result_3d['confidence'] > 0.756 and 'circle_3d' in result_3d and 'normal' in result_3d['circle_3d']:
            gaze_normal = result_3d['circle_3d']['normal']
            gaze_point = self.predict_gaze_point(gaze_normal)
            if gaze_point is not None:
                self.shared_gaze_data.update(gaze_point)
                self.debug_info = f"Predicted gaze point: {gaze_point}"
            else:
                self.debug_info = "Invalid gaze prediction"
        else:
            self.debug_info = "Low confidence or missing gaze data"
        
        return result_3d

    def predict_gaze_point(self, gaze_normal):
        if self.lr_model is None:
            return None
        
        prediction = self.lr_model.predict([gaze_normal])[0]
        return tuple(map(int, prediction))

    def cam_preview(self):
        cam = cv2.VideoCapture(self.stream_url)
        if not cam.isOpened():
            print(f"Error: Could not open stream {self.stream_url}")
            return

        frame_count = 0

        while self.running:
            ret, frame = cam.read()
            if not ret:
                print(f"Failed to grab frame from {self.preview_name}")
                break

            # Resize frame to match desired resolution
            frame = cv2.resize(frame, (self.resolution[0], self.resolution[1]))

            if self.is_eye_cam:
                result_3d = self.process_eye_frame(frame, frame_count)
            else:
                if self.camera_matrix is not None and self.dist_coeffs is not None:
                    frame = cv2.undistort(frame, self.camera_matrix, self.dist_coeffs)

                gaze_point = self.shared_gaze_data.get()
                if gaze_point:
                    gaze_point = tuple(map(int, gaze_point))
                    if 0 <= gaze_point[0] < frame.shape[1] and 0 <= gaze_point[1] < frame.shape[0]:
                        cv2.circle(frame, gaze_point, 15, (0, 0, 255), -1)
                        self.debug_info = f"Drawing gaze at: {gaze_point}"
                    else:
                        self.debug_info = f"Gaze point out of bounds: {gaze_point}"
                else:
                    self.debug_info = "No gaze point available"

            cv2.putText(frame, self.debug_info, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

            if not self.is_eye_cam:
                cv2.imshow(self.preview_name, frame)
            if cv2.waitKey(1) & 0xFF == 27:  # Press 'Esc' to exit
                break

            frame_count += 1

        cam.release()
        cv2.destroyWindow(self.preview_name)

class GazeControlThread(threading.Thread):
    def __init__(self, shared_gaze_data, disable_failsafe=False):
        threading.Thread.__init__(self)
        self.shared_gaze_data = shared_gaze_data
        self.running = True
        self.last_press_time = 0
        self.left_pressed = False
        self.right_pressed = False

    def run(self):
        while self.running:
            try:
                gaze_point = self.shared_gaze_data.get()
                if gaze_point:
                    x = gaze_point[0]

                    if x < 240:
                        if not self.left_pressed:
                            keyboard.press('a')
                            self.left_pressed = True
                        if self.right_pressed:
                            keyboard.release('d')
                            self.right_pressed = False
                    elif x > 420:
                        if not self.right_pressed:
                            keyboard.press('d')
                            self.right_pressed = True
                        if self.left_pressed:
                            keyboard.release('a')
                            self.left_pressed = False
                    else:
                        if self.left_pressed:
                            keyboard.release('a')
                            self.left_pressed = False
                        if self.right_pressed:
                            keyboard.release('d')
                            self.right_pressed = False

            except Exception as e:
                print(f"An error occurred in gaze control: {e}")

            time.sleep(0.1)  # Small delay to prevent excessive CPU usage

    def stop(self):
        self.running = False
        # Ensure keys are released when stopping
        if self.left_pressed:
            keyboard.release('a')
        if self.right_pressed:
            keyboard.release('d')

def load_linear_regression_model():
    try:
        lr_model = joblib.load('linearregressionmodelbucket5.joblib')
        print("Linear Regression model loaded successfully.")
        return lr_model
    except Exception as e:
        print(f"Failed to load Linear Regression model: {e}")
        print("Falling back to default gaze projection method.")
        return None

class WindowNotFoundError(Exception):
    """Raised when a specified window is not found."""
    pass
def bring_window_to_top(window_name):
    def window_dict_handler(hwnd, top_windows):
        top_windows[hwnd] = win32gui.GetWindowText(hwnd)
    tw, expt = {}, True
    win32gui.EnumWindows(window_dict_handler, tw)
    for handle in tw:
        if tw[handle] == window_name:
            win32gui.ShowWindow(handle, win32con.SW_NORMAL)
            win32gui.BringWindowToTop(handle)
            win32gui.SetForegroundWindow(handle)
            expt = False
    if expt:
        raise WindowNotFoundError(f"'{window_name}' does not appear to be a window.")

def main(args):
    shared_gaze_data = SharedGazeData()

    camera_matrix = np.array([[343.34511283, 0.0, 327.80111243],
                              [0.0, 342.79698299, 231.06509007],
                              [0.0, 0.0, 1.0]])
    dist_coeffs = np.array([0, 0, 0, -0.001, -0.0])

    # Load the Linear Regression model
    lr_model = load_linear_regression_model()

    eye_cam_thread = CamThread("Eye Camera", args.eye_stream, args.eye_res, 
                               is_eye_cam=True, focal_length=args.focal_length, 
                               shared_gaze_data=shared_gaze_data,
                               lr_model=lr_model)
    #front_cam_thread = CamThread("Front Camera", args.front_stream, args.front_res, 
    #                             shared_gaze_data=shared_gaze_data,
    #                             camera_matrix=camera_matrix, dist_coeffs=dist_coeffs)
    gaze_control_thread = GazeControlThread(shared_gaze_data, disable_failsafe=args.disable_failsafe)
    bring_window_to_top("Roblox")
    eye_cam_thread.start()
    #front_cam_thread.start()
    gaze_control_thread.start()

    try:
        eye_cam_thread.join()
        #front_cam_thread.join()
        gaze_control_thread.join()
    except KeyboardInterrupt:
        print("Stopping threads...")
        eye_cam_thread.stop()
        #front_cam_thread.stop()
        gaze_control_thread.stop()
        eye_cam_thread.join()
        #front_cam_thread.join()
        gaze_control_thread.join()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dual camera eye tracking system")
    parser.add_argument("--eye_stream", type=str, default="http://192.168.172.53:8081/?action=stream",
                        help="Eye camera stream URL")
    #parser.add_argument("--front_stream", type=str, default="http://192.168.1.120:8080/?action=stream",
    #                    help="Front camera stream URL")
    parser.add_argument("--eye_res", nargs=2, type=int, default=[320, 240], help="Eye camera resolution")
    #parser.add_argument("--front_res", nargs=2, type=int, default=[640, 480], help="Front camera resolution")
    parser.add_argument("--focal_length", type=float, default=84, help="Focal length of the eye camera")
    parser.add_argument("--disable_failsafe", action="store_true", help="Disable PyAutoGUI fail-safe")
    args = parser.parse_args()
    
    main(args)