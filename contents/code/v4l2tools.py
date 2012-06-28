#!/usr/bin/env python2
# -*- coding: utf-8 -*-
#
# Webcamod, Show and take Photos with your webcam.
# Copyright (C) 2011  Gonzalo Exequiel Pedone
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with This program. If not, see <http://www.gnu.org/licenses/>.
#
# Email   : hipersayan.x@gmail.com
# Web-Site: http://hipersayanx.blogspot.com/

import os
import sys
import ctypes
import fcntl
import subprocess
import tempfile

from PyQt4 import QtCore, QtGui
from v4l2 import v4l2

class V4L2Tools(QtCore.QObject):
    devicesModified = QtCore.pyqtSignal()

    def __init__(self, parent=None, watchDevices=False):
        QtCore.QObject.__init__(self, parent)
        self.hasPyGst = False
        self.gobject = None
        self.pygst = None
        self.gst = None

        self.camerabin = None
        self.fdDisplay = -1
        self.fdSink = -1
        self.videoSource = None

        self.fps = 30
        self.current_dev_name = ''
        self.videoSize = QtCore.QSize()
        self.effects = []
        self.recording = False

        if watchDevices:
            self.fsWatcher = QtCore.QFileSystemWatcher(['/dev'], self)
            self.fsWatcher.directoryChanged.connect(self.devicesModified)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stopCurrentDevice()

        return True

    def currentDevice(self):
        return self.current_dev_name

    def fcc2s(self, val=0):
        s = ''

        s += chr(val & 0xff)
        s += chr((val >> 8) & 0xff)
        s += chr((val >> 16) & 0xff)
        s += chr((val >> 24) & 0xff)

        return s

    # videoFormats(self, dev_name='/dev/video0') -> (width, height, fourcc)
    def videoFormats(self, dev_name='/dev/video0'):
        formats = []

        try:
            dev_fd = os.open(dev_name, os.O_RDWR | os.O_NONBLOCK, 0)
        except:
            return formats

        for type in [v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE,
                     v4l2.V4L2_BUF_TYPE_VIDEO_OUTPUT,
                     v4l2.V4L2_BUF_TYPE_VIDEO_OVERLAY]:
            fmt = v4l2.v4l2_fmtdesc()
            fmt.index = 0
            fmt.type = type

            try:
                while fcntl.ioctl(dev_fd, v4l2.VIDIOC_ENUM_FMT, fmt) >= 0:
                    frmsize = v4l2.v4l2_frmsizeenum()
                    frmsize.pixel_format = fmt.pixelformat
                    frmsize.index = 0

                    try:
                        while fcntl.ioctl(dev_fd,
                                          v4l2.VIDIOC_ENUM_FRAMESIZES,
                                          frmsize) >= 0:
                            if frmsize.type == v4l2.V4L2_FRMSIZE_TYPE_DISCRETE:
                                formats.append((frmsize.discrete.width,
                                                frmsize.discrete.height,
                                                fmt.pixelformat))

                            frmsize.index += 1
                    except:
                        pass

                    fmt.index += 1
            except:
                pass

        os.close(dev_fd)

        return formats

    def currentVideoFormat(self, dev_name='/dev/video0'):
        try:
            dev_fd = os.open(dev_name, os.O_RDWR | os.O_NONBLOCK, 0)
        except:
            return tuple()

        fmt = v4l2.v4l2_format()
        fmt.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE

        if fcntl.ioctl(dev_fd, v4l2.VIDIOC_G_FMT, fmt) == 0:
            videoFormat = (fmt.fmt.pix.width,
                        fmt.fmt.pix.height,
                        fmt.fmt.pix.pixelformat)
        else:
            videoFormat = tuple()

        os.close(dev_fd)

        return videoFormat

    def setVideoFormat(self, dev_name='/dev/video0', videoFormat=tuple()):
        try:
            dev_fd = os.open(dev_name, os.O_RDWR | os.O_NONBLOCK, 0)
        except:
            return False

        fmt = v4l2.v4l2_format()
        fmt.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE

        if fcntl.ioctl(dev_fd, v4l2.VIDIOC_G_FMT, fmt) == 0:
            fmt.fmt.pix.width = videoFormat[0]
            fmt.fmt.pix.height = videoFormat[1]
            fmt.fmt.pix.pixelformat = videoFormat[2]

            try:
                fcntl.ioctl(dev_fd, v4l2.VIDIOC_S_FMT, fmt)
            except:
                os.close(dev_fd)
                self.startDevice(dev_name, videoFormat)

                return True

        os.close(dev_fd)

        return True

    def captureDevices(self):
        webcamsDevices = []
        devicesDir = QtCore.QDir('/dev')

        devices = devicesDir.entryList(['video*'],
                                       QtCore.QDir.System |
                                       QtCore.QDir.Readable |
                                       QtCore.QDir.Writable |
                                       QtCore.QDir.NoSymLinks |
                                       QtCore.QDir.NoDotAndDotDot |
                                       QtCore.QDir.CaseSensitive,
                                       QtCore.QDir.Name)

        fd = QtCore.QFile()
        capability = v4l2.v4l2_capability()

        for device in devices:
            fd.setFileName(devicesDir.absoluteFilePath(device))

            if fd.open(QtCore.QIODevice.ReadWrite):
                fcntl.ioctl(fd.handle(), v4l2.VIDIOC_QUERYCAP, capability)

                if capability.capabilities & v4l2.V4L2_CAP_VIDEO_CAPTURE:
                    webcamsDevices.append((str(fd.fileName()), capability.card))

                fd.close()

        return webcamsDevices

    # queryControl(dev_fd, queryctrl) ->
    #                       (name, type, min, max, step, default, value, menu)
    def queryControl(self, dev_fd, queryctrl):
        ctrl = v4l2.v4l2_control(0)
        ext_ctrl = v4l2.v4l2_ext_control(0)
        ctrls = v4l2.v4l2_ext_controls(0)

        if queryctrl.flags & v4l2.V4L2_CTRL_FLAG_DISABLED:
            return tuple()

        if queryctrl.type == v4l2.V4L2_CTRL_TYPE_CTRL_CLASS:
            return tuple()

        ext_ctrl.id = queryctrl.id
        ctrls.ctrl_class = v4l2.V4L2_CTRL_ID2CLASS(queryctrl.id)
        ctrls.count = 1
        ctrls.controls = ctypes.pointer(ext_ctrl)

        if (v4l2.V4L2_CTRL_ID2CLASS(queryctrl.id) != v4l2.V4L2_CTRL_CLASS_USER \
            and queryctrl.id < v4l2.V4L2_CID_PRIVATE_BASE):
            if fcntl.ioctl(dev_fd, v4l2.VIDIOC_G_EXT_CTRLS, ctrls):
                return tuple()
        else:
            ctrl.id = queryctrl.id

            if fcntl.ioctl(dev_fd, v4l2.VIDIOC_G_CTRL, ctrl):
                return tuple()

            ext_ctrl.value = ctrl.value

        qmenu = v4l2.v4l2_querymenu(0)
        qmenu.id = queryctrl.id
        menu = []

        if queryctrl.type == v4l2.V4L2_CTRL_TYPE_MENU:
            for i in range(queryctrl.maximum + 1):
                qmenu.index = i

                if fcntl.ioctl(dev_fd, v4l2.VIDIOC_QUERYMENU, qmenu):
                    continue

                menu.append(qmenu.name)

        return (queryctrl.name,
                queryctrl.type,
                queryctrl.minimum,
                queryctrl.maximum,
                queryctrl.step,
                queryctrl.default,
                ext_ctrl.value,
                menu)

    def listControls(self, dev_name='/dev/video0'):
        queryctrl = v4l2.v4l2_queryctrl(v4l2.V4L2_CTRL_FLAG_NEXT_CTRL)
        controls = []

        try:
            dev_fd = os.open(dev_name, os.O_RDWR | os.O_NONBLOCK, 0)
        except:
            return controls

        try:
            while fcntl.ioctl(dev_fd, v4l2.VIDIOC_QUERYCTRL, queryctrl) == 0:
                control = self.queryControl(dev_fd, queryctrl)

                if control != tuple():
                    controls.append(control)

                queryctrl.id |= v4l2.V4L2_CTRL_FLAG_NEXT_CTRL
        except:
            pass

        if queryctrl.id != v4l2.V4L2_CTRL_FLAG_NEXT_CTRL:
            os.close(dev_fd)

            return controls

        for id in range(v4l2.V4L2_CID_USER_BASE, v4l2.V4L2_CID_LASTP1):
            queryctrl.id = id

            if fcntl.ioctl(dev_fd, v4l2.VIDIOC_QUERYCTRL, queryctrl) == 0:
                control = self.queryControl(dev_fd, queryctrl)

                if control != tuple():
                    controls.append(control)

        queryctrl.id = v4l2.V4L2_CID_PRIVATE_BASE

        while fcntl.ioctl(dev_fd, v4l2.VIDIOC_QUERYCTRL, queryctrl) == 0:
            control = self.queryControl(dev_fd, queryctrl)

            if control != tuple():
                controls.append(control)

            queryctrl.id += 1

        os.close(dev_fd)

        return controls

    def findControls(self, dev_fd):
        qctrl = v4l2.v4l2_queryctrl(v4l2.V4L2_CTRL_FLAG_NEXT_CTRL)
        controls = {}

        try:
            while fcntl.ioctl(dev_fd, v4l2.VIDIOC_QUERYCTRL, qctrl) == 0:
                if qctrl.type != v4l2.V4L2_CTRL_TYPE_CTRL_CLASS and \
                   not (qctrl.flags & v4l2.V4L2_CTRL_FLAG_DISABLED):
                    controls[qctrl.name] = qctrl.id

                qctrl.id |= v4l2.V4L2_CTRL_FLAG_NEXT_CTRL
        except:
            pass

        if qctrl.id != v4l2.V4L2_CTRL_FLAG_NEXT_CTRL:
            return controls

        for id in range(v4l2.V4L2_CID_USER_BASE, v4l2.V4L2_CID_LASTP1):
            qctrl.id = id

            if fcntl.ioctl(dev_fd, v4l2.v4l2.VIDIOC_QUERYCTRL, qctrl) == 0 and \
               not (qctrl.flags & v4l2.V4L2_CTRL_FLAG_DISABLED):
                controls[qctrl.name] = qctrl.id

        qctrl.id = v4l2.V4L2_CID_PRIVATE_BASE

        while fcntl.ioctl(dev_fd, v4l2.VIDIOC_QUERYCTRL, qctrl) == 0:
            if not (qctrl.flags & v4l2.V4L2_CTRL_FLAG_DISABLED):
                controls[qctrl.name] = qctrl.id

            qctrl.id += 1

        return controls

    def setControls(self, dev_name='/dev/video0', controls={}):
        try:
            dev_fd = os.open(dev_name, os.O_RDWR | os.O_NONBLOCK, 0)
        except:
            return False

        ctrl2id = self.findControls(dev_fd)
        mpeg_ctrls = []
        user_ctrls = []

        for control in controls:
            ctrl = v4l2.v4l2_ext_control(0)
            ctrl.id = ctrl2id[control]
            ctrl.value = controls[control]

            if v4l2.V4L2_CTRL_ID2CLASS(ctrl.id) == v4l2.V4L2_CTRL_CLASS_MPEG:
                mpeg_ctrls.append(ctrl)
            else:
                user_ctrls.append(ctrl)

        for user_ctrl in user_ctrls:
            ctrl = v4l2.v4l2_control()
            ctrl.id = user_ctrl.id
            ctrl.value = user_ctrl.value
            fcntl.ioctl(dev_fd, v4l2.VIDIOC_S_CTRL, ctrl)

        if mpeg_ctrls != []:
            ctrls = v4l2.v4l2_ext_controls(0)
            ctrls.ctrl_class = v4l2.V4L2_CTRL_CLASS_MPEG
            ctrls.count = len(mpeg_ctrls)
            ctrls.controls = ctypes.pointer(mpeg_ctrls[0])
            fcntl.ioctl(dev_fd, v4l2.VIDIOC_S_EXT_CTRLS, ctrls)

        os.close(dev_fd)

        return True

    def setEffects(self, effects=[]):
        self.effects = [str(effect) for effect in effects]

        if self.effects == []:
            effectsBin = None
        else:
            effectsBinSrc = 'ffmpegcolorspace ! ' + ' ! ffmpegcolorspace ! '.join(self.effects) + ' ! ffmpegcolorspace'
            effectsBin = self.gst.parse_bin_from_description(effectsBinSrc, True)

        dev_name = self.current_dev_name
        self.stopCurrentDevice()
        self.camerabin.set_property('video-source-filter', effectsBin)
        self.startDevice(dev_name)

    def currentEffects(self):
        return self.effects

    def reset(self, dev_name='/dev/video0'):
        videoFormats = self.videoFormats(dev_name)
        self.setVideoFormat(dev_name, videoFormats[0])

        controls = self.listControls(dev_name)

        self.setControls(dev_name,
                         {control[0]: control[5] for control in controls})

    def startDevice(self, dev_name='/dev/video0', forcedFormat=tuple()):
        if not self.hasPyGst:
            try:
                self.gobject = __import__('gobject')
                self.pygst = __import__('pygst')

                self.pygst.require('0.10')

                self.gst = __import__('gst')

                self.gobject.threads_init()

                self.camerabin = self.gst.element_factory_make('camerabin')
                self.camerabin.set_property('mode', 1)

                self.fdDisplay, self.fdSink = os.pipe()
                displayBin = self.gst.parse_bin_from_description('ffmpegcolorspace ! capsfilter caps=video/x-raw-rgb,bpp=24,depth=24 ! fdsink fd={}'.format(self.fdSink), True)
                self.camerabin.set_property('viewfinder-sink', displayBin)

                self.videoSource = self.gst.element_factory_make('v4l2src')
                self.camerabin.set_property('video-source', self.videoSource)

                audioBin = self.gst.parse_bin_from_description('alsasrc name=audio ! queue ! audioconvert ! queue', True)
                audio = audioBin.get_by_name('audio')
                audio.set_property('device', 'plughw:0,0')
                self.camerabin.set_property('audio-source', audioBin)

                videoEncoder = self.gst.element_factory_make('vp8enc')
                videoEncoder.set_property('quality', 10)
                videoEncoder.set_property('speed', 7)
                videoEncoder.set_property('bitrate', 1000000000)
                self.camerabin.set_property('video-encoder', videoEncoder)

                videoMuxer = self.gst.element_factory_make('webmmux')
                self.camerabin.set_property('video-muxer', videoMuxer)

                bus = self.camerabin.get_bus()
                bus.add_signal_watch()
                bus.connect('message', self.on_gst_message)

                self.hasPyGst = True
            except:
                return False

        if forcedFormat == tuple():
            fmt = self.currentVideoFormat(dev_name)

            if fmt == tuple():
                fmt = self.videoFormats(dev_name)[0]
        else:
            fmt = forcedFormat

        self.stopCurrentDevice()

        self.videoSource.set_property('device', dev_name)
        self.camerabin.set_property('video-capture-width', fmt[0])
        self.camerabin.set_property('video-capture-height', fmt[1])
        self.camerabin.set_property('video-capture-framerate', self.gst.Fraction(self.fps, 1))

        self.videoSize = QtCore.QSize(fmt[0], fmt[1])
        self.current_dev_name = dev_name

        self.camerabin.set_state(self.gst.STATE_PLAYING)

        return True

    def stopCurrentDevice(self):
        if self.current_dev_name != '':
            self.current_dev_name = ''
            self.camerabin.set_state(self.gst.STATE_NULL)
            self.videoSize = QtCore.QSize()

    @QtCore.pyqtSlot()
    def readFrame(self):
        if self.current_dev_name != '':
            frame = os.read(self.fdDisplay, 3 * self.videoSize.width()
                                              * self.videoSize.height())

            return QtGui.QImage(frame,
                                self.videoSize.width(),
                                self.videoSize.height(),
                                QtGui.QImage.Format_RGB888)
        else:
            return QtGui.QImage()

    @QtCore.pyqtSlot()
    def on_gst_message(self, bus, message):
        pass

    @QtCore.pyqtSlot()
    def isRecording(self):
        return self.recording

    @QtCore.pyqtSlot()
    def startVideoRecord(self, fileName=''):
        self.camerabin.set_property('filename', 'webcam.webm')

        videoEncoder = gst.element_factory_make('vp8enc')
        videoEncoder.set_property('quality', 10)
        videoEncoder.set_property('speed', 7)
        videoEncoder.set_property('bitrate', 1000000000)
        self.camerabin.set_property('video-encoder', videoEncoder)

        videoMuxer = gst.element_factory_make('webmmux')
        self.camerabin.set_property('video-muxer', videoMuxer)

        self.camerabin.emit('capture-start')
        self.recording = True

    @QtCore.pyqtSlot()
    def stopVideoRecord(self):
        self.camerabin.emit('capture-stop')
        self.recording = True


if __name__ == '__main__':
    app = QtGui.QApplication(sys.argv)
    tools = V4L2Tools()
    tools.startDevice('/dev/video0')

    for i in range(100):
        tools.readFrame()
        QtCore.QCoreApplication.processEvents()

    tools.stopCurrentDevice()
    app.exec_()