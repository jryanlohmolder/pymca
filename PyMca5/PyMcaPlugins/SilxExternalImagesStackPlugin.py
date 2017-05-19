# /*#########################################################################
# Copyright (C) 2004-2017 V.A. Sole, European Synchrotron Radiation Facility
#
# This file is part of the PyMca X-ray Fluorescence Toolkit developed at
# the ESRF by the Software group.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
# ###########################################################################*/
"""Plugin allowing to view an external image in a plot widget, with tools to
crop and rotate the image.

The mask of the plot widget is synchronized with the master stack widget."""

__authors__ = ["V.A. Sole", "P. Knobel"]
__contact__ = "sole@esrf.fr"
__license__ = "MIT"


import os
import numpy

from PyMca5 import StackPluginBase
from PyMca5.PyMcaGui import PyMcaQt as qt
from PyMca5.PyMcaIO import EDFStack
from PyMca5.PyMcaGui.io import PyMcaFileDialogs
from PyMca5.PyMcaGui.pymca import SilxExternalImagesWindow
from PyMca5.PyMcaGui import PyMca_Icons as PyMca_Icons

from silx.image.bilinear import BilinearImage


# TODO: in the future maybe we want to change the RGB correlator to accept different image
# sizes and we won't need resizing anymore
def resize_image(original_image, new_shape):
    """Return resized image

    :param original_image:
    :param tuple(int) new_shape: New image shape (rows, columns)
    :return: New resized image, as a 2D numpy array
    """
    bilinimg = BilinearImage(original_image)

    row_array, column_array = numpy.meshgrid(
            numpy.linspace(0, original_image.shape[0], new_shape[0]),
            numpy.linspace(0, original_image.shape[1], new_shape[1]),
            indexing="ij")

    interpolated_values = bilinimg.map_coordinates((row_array, column_array))

    interpolated_values.shape = new_shape
    return interpolated_values


class SilxExternalImagesStackPlugin(StackPluginBase.StackPluginBase):
    def __init__(self, stackWindow):
        StackPluginBase.StackPluginBase.__init__(self, stackWindow)
        self.methodDict = {'Load': [self._loadImageFiles,
                                    "Load Images",
                                    PyMca_Icons.fileopen],
                           'Show': [self._showWidget,
                                    "Show Image Browser",
                                    PyMca_Icons.brushselect]}
        self.__methodKeys = ['Load', 'Show']
        self.widget = None

    def stackUpdated(self):
        self.widget = None

    def selectionMaskUpdated(self):
        if self.widget is None:
            return
        if self.widget.isHidden():
            return
        mask = self.getStackSelectionMask()
        self.widget.setSelectionMask(mask)

    def onWidgetSignal(self, ddict):
        """triggered by self.widget.sigMaskImageWidget"""
        if ddict['event'] == "selectionMaskChanged":
            self.setStackSelectionMask(ddict["current"])
        elif ddict['event'] == "removeImageClicked":
            self.removeImage(ddict['title'])
        elif ddict['event'] in ["addImageClicked", "replaceImageClicked"]:
            # resize external image to the stack shape
            stack_image_shape = self._getStackImageShape()
            external_image = ddict['image']
            resized_image = resize_image(external_image, stack_image_shape)

            if ddict['event'] == "addImageClicked":
                self.addImage(resized_image, ddict['title'])
            elif ddict['event'] == "replaceImageClicked":
                self.replaceImage(resized_image, ddict['title'])
        elif ddict['event'] == "resetSelection":
            self.setStackSelectionMask(None)

    #Methods implemented by the plugin
    def getMethods(self):
        if self.widget is None:
            return [self.__methodKeys[0]]
        else:
            return self.__methodKeys

    def getMethodToolTip(self, name):
        return self.methodDict[name][1]

    def getMethodPixmap(self, name):
        return self.methodDict[name][2]

    def applyMethod(self, name):
        return self.methodDict[name][0]()

    def _loadImageFiles(self):
        if self.getStackDataObject() is None:
            return
        getfilter = True
        fileTypeList = ["PNG Files (*png)",
                        "JPEG Files (*jpg *jpeg)",
                        "IMAGE Files (*)",
                        "EDF Files (*edf)",
                        "EDF Files (*ccd)",
                        "EDF Files (*)"]
        message = "Open image file"
        filenamelist, filefilter = PyMcaFileDialogs.getFileList(
                parent=None,
                filetypelist=fileTypeList,
                message=message,
                getfilter=getfilter,
                single=False,
                currentfilter=None)
        if not filenamelist:
            return
        imagelist = []
        imagenames = []
        mask = self.getStackSelectionMask()
        if mask is None:
            r, n = self.getStackROIImagesAndNames()
            shape = r[0].shape
        else:
            shape = mask.shape

        self.widget = SilxExternalImagesWindow.SilxExternalImagesWindow()
        self.widget.sigMaskImageWidget.connect(
                self.onWidgetSignal)

        if filefilter.startswith("EDF"):
            for filename in filenamelist:
                # read the edf file
                edf = EDFStack.EdfFileDataSource.EdfFileDataSource(filename)

                # the list of images
                keylist = edf.getSourceInfo()['KeyList']
                if len(keylist) < 1:
                    msg = qt.QMessageBox(None)
                    msg.setIcon(qt.QMessageBox.Critical)
                    msg.setText("Cannot read image from file")
                    msg.exec_()
                    return

                for key in keylist:
                    #get the data
                    dataObject = edf.getDataObject(key)
                    data = dataObject.data
                    if data.shape[0] not in shape or data.shape[1] not in shape:
                        # print("Ignoring %s (inconsistent shape)" % key)
                        continue
                    imagename = dataObject.info.get('Title', "")
                    if imagename != "":
                        imagename += " "
                    imagename += os.path.basename(filename) + " " + key
                    imagelist.append(data)
                    imagenames.append(imagename)
            if not imagelist:
                msg = qt.QMessageBox(None)
                msg.setIcon(qt.QMessageBox.Critical)
                msg.setText("Cannot read a valid image from the file")
                msg.exec_()
                return
        else:
            # Try pure Image formats
            for filename in filenamelist:
                image = qt.QImage(filename)
                if image.isNull():
                    msg = qt.QMessageBox(self)
                    msg.setIcon(qt.QMessageBox.Critical)
                    msg.setText("Cannot read file %s as an image" % filename)
                    msg.exec_()
                    return
                imagelist.append(image)
                imagenames.append(os.path.basename(filename))

            if not imagelist:
                msg = qt.QMessageBox(None)
                msg.setIcon(qt.QMessageBox.Critical)
                msg.setText("Cannot read a valid image from the file")
                msg.exec_()
                return

            for i, image in enumerate(imagelist):
                imagelist[i] = self.qImageToRgba(image)

        nimages = len(imagelist)
        image_shape = self._getStackImageShape()
        origin, scale = self._getStackOriginScale()

        h = scale[1] * image_shape[0]
        w = scale[0] * image_shape[1]

        # add the stack image for mask operation
        self.widget.setImages([self.getStackOriginalImage()],
                              labels=["stack data"],
                              origin=origin, width=w, height=h)
        self.widget.plot.getImage("current").setAlpha(0)

        # add the external image
        self.widget.setBackgroundImages(imagelist,
                                        labels=imagenames,
                                        origins=[origin] * nimages,
                                        widths=[w] * nimages,
                                        heights=[h] * nimages)
        self.widget.plot.setGraphTitle(imagenames[0])

        self._showWidget()

    def _getStackOriginScale(self):
        info = self.getStackInfo()

        xscale = info.get("xScale", [0.0, 1.0])
        yscale = info.get("yScale", [0.0, 1.0])

        # from here on, scale and origin are defined in the silx sense
        origin = xscale[0], yscale[0]
        scale = xscale[1], yscale[1]

        return origin, scale

    def _getStackImageShape(self):
        """Return 2D image shape deducted from 3D stack shape"""
        # info = self.getStackInfo()
        # image_shape = list(self.getStackData().shape)
        # # remove dimension associated with frame index
        # del image_shape[info.get("McaIndex", -1)]
        image_shape = list(self.getStackOriginalImage().shape)
        return image_shape

    def _showWidget(self):
        if self.widget is None:
            return

        #Show
        self.widget.show()
        self.widget.raise_()

        #update
        self.selectionMaskUpdated()

    @staticmethod
    def qImageToRgba(qimage):
        width = qimage.width()
        height = qimage.height()
        if qimage.format() == qt.QImage.Format_Indexed8:
            pixmap0 = numpy.fromstring(qimage.bits().asstring(width * height),
                                       dtype=numpy.uint8)
            pixmap = numpy.zeros((height * width, 4), numpy.uint8)
            pixmap[:, 0] = pixmap0[:]
            pixmap[:, 1] = pixmap0[:]
            pixmap[:, 2] = pixmap0[:]
            pixmap[:, 3] = 255
            pixmap.shape = height, width, 4
        else:
            qimage = qimage.convertToFormat(qt.QImage.Format_ARGB32)
            pixmap = numpy.fromstring(qimage.bits().asstring(width * height * 4),
                                      dtype=numpy.uint8)
            pixmap.shape = height, width, -1
            # Qt uses BGRA, convert to RGBA   # TODO: check this (qt doc says 0xAARRGGBB)
            tmpBuffer = numpy.array(pixmap[:, :, 0], copy=True, dtype=pixmap.dtype)
            pixmap[:, :, 0] = pixmap[:, :, 2]
            pixmap[:, :, 2] = tmpBuffer

        return pixmap


MENU_TEXT = "Silx External Images Tool"


def getStackPluginInstance(stackWindow, **kw):
    ob = SilxExternalImagesStackPlugin(stackWindow)
    return ob
