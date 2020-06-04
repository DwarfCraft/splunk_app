"""
(C) 2020 Splunk Inc. All rights reserved.

Constants for dimensions required for workspace arrangement and visualizations.
"""


AR_DASHBOARD_PANEL_LIMIT = 20


class NodeDimensions(object):
    depth = 0.0001


class ModelNodeDimensions(NodeDimensions):
    height = 0.045
    width = 0.045


class TextNoteDimensions(NodeDimensions):
    height = 0.045
    width = 0.09


class AudioNoteDimensions(NodeDimensions):
    height = 0.06
    width = 0.098


class PDFNoteDimensions(NodeDimensions):
    height = 0.098
    width = 0.06


class ImageNoteDimensions(NodeDimensions):
    height = 0.098
    width = 0.098


class VideoNoteDimensions(NodeDimensions):
    height = 0.098
    width = 0.098


class PlaybookDimensions(NodeDimensions):
    height = 0.0384
    width = 0.126


class WorkspaceDimensions(NodeDimensions):
    height = 0.075
    width = 0.20
    padding = 0.008
