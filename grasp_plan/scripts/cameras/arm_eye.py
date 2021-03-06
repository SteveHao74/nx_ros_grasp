'''
@Description: In User Settings Edit
@Author: Lai
@Date: 2019-11-04 13:14:06
@LastEditTime : 2020-01-15 20:53:11
@LastEditors  : Lai
'''
import python3_in_ros
import os
import sys
import shutil
from tkinter.constants import NO
import cv2
import cv2.aruco as aruco
import numpy as np
import tkinter as tk
from matplotlib import pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg   # NavigationToolbar2TkAgg
from armeye_calibration import eye_arm_calibrate
###
import rospy
import math
import tf
import geometry_msgs.msg
from scipy.spatial.transform import Rotation as R

file_path = os.path.dirname(os.path.abspath(__file__))
root_path = os.path.abspath(os.path.join(file_path, '..'))
print(root_path)
sys.path.append(root_path)
try:
    # from utils.robotiq_85 import Robotiq85
    # from utils.robotiq_85 import Robotiq85
    # from utils.ur_status import URStatus
    # from utils.primesense_sensor import PrimesenseSensor
    # from utils.realsenseL515 import RealsenseSensor

    # from utils.robotiq import Robotiq140
    # from utils.ur_status import URStatus
    from realsense_sensor import RealsenseSensor
except Exception as e:
    print('import utils error')
    raise e


# 标定物的尺寸
OBJ_SIZE = (7, 7)
# 标定点之间的距离, 单位mm
# 对相机的内参没有影响, 但是对目标相对相机位置有影响
OBJ_DIS = 30


class ArmEyeUI(object):
    def __init__(self, out_path, camera, mtx_path=None):
        self.save = False
        self.images = []
        self.arm_s = []
        self.auto_counter = 0
        self.tf_listener = tf.TransformListener()
        # try:
        #     self.ur_status = URStatus()
        #     # self.gripper = Robotiq140()
        # except:
        #     print('check arm and gripper has connected !!!!!!')
        self.out_path = os.path.abspath(out_path)
        if not os.path.exists(self.out_path):
            os.makedirs(self.out_path)
        if mtx_path:
            self.mtx = np.load(os.path.join(mtx_path, 'mtx.npy'))
            self.dist = np.load(os.path.join(mtx_path, 'dist.npy'))
        else:
            self.mtx = camera.mtx
            self.dist = camera.dist
            np.save("real_camera_intrinsic.npy",self.mtx)
        print('mtx:\n', self.mtx)
        print('dist:\n', self.dist)
        self.camera = camera
        self.make_ui()
        self.video_loop()
        self.root.mainloop()

    def make_ui(self):
        self.root = tk.Tk()  # 创建主窗体
        self.root.title('Calibrater')
        self.auto = tk.IntVar()
        f = tk.Frame(self.root)
        f.pack(side=tk.LEFT)
        self.create_form(f).pack(side=tk.TOP, ipadx=5, ipady=5,
                                 padx=5, pady=5)  # 将figure显示在tkinter窗体上面
        self.add_button(f).pack(pady=5)
        self.add_ur_frame(self.root).pack(side=tk.RIGHT, ipadx=5)

    def add_ur_frame(self, frame):
        def add_info(frame, name, row):
            l0 = tk.Label(frame, text=f'{name}:', font=('Arial', 12))
            l0.grid(row=row, sticky=tk.E, ipady=5)
            text = tk.StringVar()
            text.set('%03.3f' % (0))
            l1 = tk.Label(frame, textvariable=text, font=('Arial', 12))
            l1.grid(row=row, column=1, sticky=tk.W)
            return text
        ur_frame = tk.Frame(frame)
        l0 = tk.Label(ur_frame, text='UR5 Info', font=('Arial', 16))
        l0.grid(row=0, ipady=5, columnspan=2)
        l1 = tk.Label(ur_frame, text='IP:', font=('Arial', 12))
        l1.grid(row=1, sticky=tk.E, ipady=5)
        self.ur_IP = tk.StringVar(value='192.168.1.104')
        e1 = tk.Entry(ur_frame, bd=1, textvariable=self.ur_IP, font=('Arial', 12), width=12)
        e1.grid(row=1, column=1)
        # self.ur_text = dict()
        for i, n in enumerate('X Y Z rx ry rz'.split()):
            text = add_info(ur_frame, n, i+2)
            # self.ur_text[n] = text
        l3 = tk.Label(ur_frame, text='Robotiq140', font=('Arial', 16))
        l3.grid(row=8, ipady=5, columnspan=2)
        self.rq_width = add_info(ur_frame, 'W', 9)
        b0 = tk.Button(ur_frame, text='open', font=('Arial', 12),
                       width=12, height=1, command=self.gripper_open)
        b0.grid(row=10, ipady=5, pady=5, columnspan=2)
        b1 = tk.Button(ur_frame, text='close', font=('Arial', 12),
                       width=12, height=1, command=self.gripper_close)
        b1.grid(row=11, ipady=5, pady=5, columnspan=2)
        l4 = tk.Label(ur_frame, text='Eye_Hand', font=('Arial', 16))
        l4.grid(row=12, ipady=5, columnspan=2)
        self.is_eye_in_hand = tk.IntVar()
        rb0 = tk.Radiobutton(ur_frame, text='eye_in_hand', value=1,
                             variable=self.is_eye_in_hand, font=('Arial', 12))
        rb0.grid(row=13, pady=5, columnspan=2)
        rb1 = tk.Radiobutton(ur_frame, text='eye_on_hand', value=0,
                             variable=self.is_eye_in_hand, font=('Arial', 12))
        rb1.grid(row=14, pady=5, columnspan=2)
        return ur_frame

    def create_form(self, frame):
        f = plt.figure(num=2, figsize=(self.camera.width//10, self.camera.height//10), dpi=8)
        f.subplots_adjust(top=1, bottom=0, left=0, right=1, hspace=0, wspace=0)
        # 把绘制的图形显示到tkinter窗口上
        self.canvas = FigureCanvasTkAgg(f, frame)
        self.canvas.draw()  # 以前的版本使用show()方法，matplotlib 2.2之后不再推荐show（）用draw代替，但是用show不会报错，会显示警告
        return self.canvas.get_tk_widget()

    def add_button(self, frame):
        """ 增加三个按键 """
        button_frame = tk.Frame(frame)
        b0 = tk.Button(button_frame, text='Clean', font=('Arial', 12),
                       width=12, height=3, command=self.clean)
        b0.pack(side=tk.LEFT, padx=5)
        b1 = tk.Button(button_frame, text='Save', font=('Arial', 12),
                       width=12, height=3, command=self.save_photo)
        b1.pack(side=tk.LEFT, padx=5)
        b2 = tk.Button(button_frame, text='Calib', font=('Arial', 12),
                       width=12, height=3, command=self.calibrate)
        b2.pack(side=tk.LEFT, padx=5)
        b3 = tk.Button(button_frame, text='Exit', font=('Arial', 12),
                       width=12, height=3, command=self.root.quit)
        b3.pack(side=tk.LEFT, padx=5)
        b4 = tk.Checkbutton(button_frame, text='auto', font=('Arial', 12),
                            variable=self.auto, onvalue=True, offvalue=False)
        b4.pack(side=tk.LEFT, padx=5)
        return button_frame

    def gripper_open(self):
        # return 
        self.gripper.open()

    def gripper_close(self):
        # return
        self.gripper.close()

    def upadte_robot_status(self):
        try:
            (trans,rot) = self.tf_listener.lookupTransform('base_link', 'end_effector_link', rospy.Time(0))
            ur_s = np.eye(4)
            ur_s[:3,:3] = R.from_quat(rot).as_matrix()
            ur_s[:3,3] = trans
        except (tf.LookupException, tf.ConnectivityException, tf.ExtrapolationException):
            print('arm or gripper read error', self.ur_IP.get().strip(), e)
            return False, None
            
        else:
            return True, ur_s

    def video_loop(self):
        if self.auto.get():
            if len(self.images) >= 30:
                # self.calibrate()
                self.auto.set(0)
            self.auto_counter = self.auto_counter + 1
            if self.auto_counter >= 8:
                self.auto_counter = 0
                self.save = True
        arm_r, arm_s = self.upadte_robot_status()
        rgb = self.camera.read_color(10)
        bgr = rgb[..., ::-1].copy()
        # bgr = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        aruco_dict = aruco.Dictionary_get(aruco.DICT_6X6_250)
        parameters = aruco.DetectorParameters_create()
        corners, ids, rejectedImgPoints = aruco.detectMarkers(
            gray, aruco_dict,  parameters=parameters)
        if ids is not None:
            rvec, tvec, _ = aruco.estimatePoseSingleMarkers(corners, 0.05, self.mtx, self.dist)
            for i in range(rvec.shape[0]):
                aruco.drawAxis(bgr, self.mtx, self.dist, rvec[i, :, :], tvec[i, :, :], 0.03)
            aruco.drawDetectedMarkers(bgr, corners)
        if self.save:
            if ids is not None and len(ids) == 4 and arm_r:
                save_path = os.path.join(self.out_path, f'{len(self.images):03d}.jpg')
                arm_path = os.path.join(self.out_path, f'{len(self.images):03d}.npy')
                cv2.imwrite(save_path, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
                np.save(arm_path, arm_s)
                self.images.append(rgb.copy())
                self.arm_s.append(np.array(arm_s))
                print('save to:', save_path)
            else:
                print('Chessboard must in the photo, and check arm')
            self.save = False
        plt.clf()
        plt.axis('off')
        # show_image = cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_RGB2BGR), None, fx=0.5, fy=0.5)
        # plt.imshow(show_image)
        plt.imshow(bgr[..., ::-1])
        plt.text(50, 50, f'num: {len(self.images):02d}', size=150,
                 color='r', style="italic", weight="light")
        self.canvas.draw()
        # 30ms后重复执行
        self.root.after(1, self.video_loop)

    def save_photo(self):
        """ 保存当前图像 """
        self.save = True

    def clean(self):
        self.images = []
        self.arm_s = []
        shutil.rmtree(self.out_path)
        os.makedirs(self.out_path)

    def calibrate(self):
        if self.images == []:  
            pic_path = os.path.join(root_path, 'cameras/arm_images_extrinsic/realsense_D435')
            files = os.listdir(pic_path)
            for file in files :
                if file[-4:]==".jpg":
                    print(file)
                    img = cv2.imread(pic_path+"/"+file)
                    self.images.append(img)
                    self.arm_s.append(np.load(pic_path+"/"+file[:3]+".npy"))
                    
        if len(self.images) < 10:
            print('need more image for calibrate!')
        else:
            cam2base = eye_arm_calibrate(self.images, self.arm_s, self.mtx, self.dist,
                                         self.is_eye_in_hand.get())
            np.save(os.path.join(self.out_path, 'cam2base.npy'), cam2base)


if __name__ == "__main__":
    # mtx_path = os.path.join(root_path, 'cameras/images_intrinsic/realsense_D435')
    out_path = os.path.join(root_path, 'cameras/arm_images_extrinsic/realsense_D435')
    rospy.init_node('arm_eye', anonymous=True)
    # mtx_path = os.path.join(root_path, 'cameras/images/primesense')
    # out_path = os.path.join(root_path, 'cameras/arm_images/primesense')
    # insces_path = os.path.join(root_path, 'cameras/images/primesense')
    if not os.path.exists(out_path):
        os.makedirs(out_path)

    
    with RealsenseSensor(align_to='color',use='color', insces_path=None) as camera:
        UI = ArmEyeUI(out_path, camera, mtx_path=None)
    # with PrimesenseSensor(insces_path=insces_path) as camera:
        # camera = None
        # UI = ArmEyeUI(out_path, camera, mtx_path)
