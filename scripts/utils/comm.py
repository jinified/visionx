#!/usr/bin/env python
import signal 

import rospy
import cv2
import numpy as np
import actionlib

from visionx.srv import *
from configs import *

class BaseComm(object):
    """Main communication class that interacts with main system"""

    def __init__(self, config):
        #Task name
        self.name = config.name
        #Get from config file
        self.detector = config.detector
        self.publishers = config.publishers
        #State of the taskrunner
        self.state = {'activated':False, 'preempted':False, 'completed':False}
        self.state['static'] = rospy.get_param('~static', False)
        self.state['alone'] = rospy.get_param('~alone', False)
        #Task specific topics
        self.visionServerTopic = "/{}/mission_to_vision".format(config.name);
        self.missionServerTopic = "/{}/vision_to_mission".format(config.name);
        #Sensor data 
        self.data = {'heading':None, 'depth':None, 'frontcam':None, 'bottomcam':None}
        #Timeout parameters
        self.navTimeout = 5

    '''Initilization'''

    def initSub(self):
        sys_msgs = self.config.sys_msgs       
        #Heading subscriber
        rospy.Subscriber(sys_msgs['heading'].topic, sys_msgs['heading'].type, self.heading_cb)
        #Depth subscriber
        rospy.Subscriber(sys_msgs['depth'].topic, sys_msgs['depth'].type, self.depth_cb)
        #Frontcam subscriber
        rospy.Subscriber(sys_msgs['frontcam_raw'].topic, sys_msgs['frontcam_raw'].type, self.cam_cb)
        #Bottomcam subscriber
        rospy.Subscriber(sys_msgs['bottomcam_raw'].topic, sys_msgs['bottomcam_raw'].type, self.cam_cb)


    def initService(self):
        """Initialize connections with mission planner"""
        #Initialize vision server and mission serviceproxy
        self.visionServer = rospy.Service(self.visionServerTopic, mission_to_vision, self.handleMission)
        self.sendMission = rospy.ServiceProxy(self.missionServerTopic, vision_to_mission)
        #Connect to mission planner
        self.sendMission.wait_for_service()

    def initNavigation(self):
        """Connect with action server in charge of vehicle navigation"""
        self.setNavServer = actionlib.SimpleActionClient(sys_msgs['navigation_server'].topic, 
                sys_msgs['navigation_server'].type)
        try:
            self.setNavServer.wait_for_server(timeout=self.navTimeout)
        except:
            pass 

    def initPID(self):
        self.setPIDServer = rospy.ServiceProxy(sys_msgs['pid'].topic, sys_msgs['pid'].type)
        #Turn on PID
        self.setPIDServer(forward=True, sidemove=True, heading=True, depth=True,    
                  pitch=True, roll=True, topside=False, navigation=False)

    def initAll(self):
        """Initializes all components related to ROS"""
        initService()
        initSub()
        initNavigation()
        if not self.state['static']:
            initPID()

    '''Callbacks'''
    
    def heading_cb(self, data):
        self.data['heading'] = data.vector.z

    def depth_cb(self, data):
        self.data['depth'] = data.depth

    def cam_cb(self, rosimg):
        pass

    def handleInterupt(self, signal, frame):
        self.state['preempted'] = True
        if self.setNavServer:
            self.setNavServer.cancel_all_goals()
        rospy.signal_shutdown("Interrupted")

    def handleMission(self, req):
        if req.start_request:
            self.state['activated'] = True
            return mission_to_visionResponse(start_response=True,
                                             abort_response=False)
        elif req.abort_request:
            self.state['preempted'] = True
            self.state['activated'] = False
            rospy.signal_shutdown("Interrupted")
            return mission_to_visionResponse(start_response=False,
                                             abort_response=True)

    '''Mission planner requests'''

    def sendTaskComplete(self):
        """Signal mission planner a task is completed"""
        if not self.state['alone']:
            self.sendMission(fail_request=False, task_complete_request=True,
                             task_complete_ctrl=controller(heading_setpoint=self.data['heading']))
        self.state['activated'] = False

    '''Navigation server requests'''
    
    def move(self,f=0.0, sm=0.0, turn=None, d=None, duration=3600):
        """Sends goal to navigation server
        Args:
            duration: time allocated for a single goal to be completed.By default wait 
            almost indefinitely
        """
        d = d if d else self.data['depth']
        if turn is None:
            turn = (turn+self.data['heading'])%360 
        goal = ControllerGoal(forward_setpoint=f, heading_setpoint=turn, 
                sidemove_setpoint=sm, depth_setpoint=d)
        self.setNavServer.send_goal(goal)
        self.setNavServer.wait_for_result(rospy.Duration(duration))

if __name__ == "__main__":
    baseComm = BaseComm();
