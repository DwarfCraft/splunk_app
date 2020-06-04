"""
(C) 2020 Splunk Inc. All rights reserved.

Operations for workspace visualization changes.
"""
import enum
import itertools
import math

from spacebridgeapp.ar.visualizations.workspace_constants import (
    AR_DASHBOARD_PANEL_LIMIT, ModelNodeDimensions, WorkspaceDimensions, TextNoteDimensions, ImageNoteDimensions,
    PDFNoteDimensions, AudioNoteDimensions, VideoNoteDimensions, PlaybookDimensions
)
from splapp_protocol.augmented_reality_pb2 import ARWorkspaceData, Matrix4x4, Vector4, Vector3

PANEL_LIMIT = 20


class Alignment(enum.Enum):
    LEFT = 'left'
    RIGHT = 'right'


def set_default_layout(ar_workspace_data_pb2):
    """
    Centers and organizes all workspace nodes.

    This will only format the first PANEL_LIMIT panels since we currently do not support more than that number iOS side.
    The remaining panels will be untouched and appended at the end of the children list.

    :param ar_workspace_data_pb2: The ARWorkspaceData to rearrange.
    :return A new workspace with default formatting applied.
    """
    formatted = ARWorkspaceData()
    formatted.CopyFrom(ar_workspace_data_pb2)

    panels_to_exclude = _pop_extra_panels(formatted)

    panels_per_row, workspace_width = _workspace_dimensions(formatted)
    _set_model_node_positions(formatted, panels_per_row, workspace_width)

    left_end, right_end = -workspace_width / 2.0, workspace_width / 2.0

    text_notes = itertools.chain((note for note in formatted.notes if note.HasField('textNote')),
                                 formatted.labels)
    left_end, right_end = _set_node_positions(text_notes, Alignment.RIGHT, TextNoteDimensions, left_end, right_end)

    image_notes = (note for note in formatted.notes if note.HasField('imageNote'))
    left_end, right_end = _set_node_positions(image_notes, Alignment.RIGHT, ImageNoteDimensions, left_end, right_end)

    pdf_notes = (note for note in formatted.notes if note.HasField('pdfNote'))
    left_end, right_end = _set_node_positions(pdf_notes, Alignment.RIGHT, PDFNoteDimensions, left_end, right_end)

    left_end, right_end = _set_node_positions(formatted.arPlaybooks, Alignment.LEFT, PlaybookDimensions,
                                              left_end, right_end)

    audio_notes = (note for note in formatted.notes if note.HasField('audioNote'))
    left_end, right_end = _set_node_positions(audio_notes, Alignment.LEFT, AudioNoteDimensions, left_end, right_end)

    video_notes = (note for note in formatted.notes if note.HasField('videoNote'))
    _set_node_positions(video_notes, Alignment.LEFT, VideoNoteDimensions, left_end, right_end)

    formatted.transformMatrix.CopyFrom(_create_transform_matrix(0, 0))
    formatted.geometryVector.CopyFrom(_create_geometry_vector(WorkspaceDimensions))

    formatted.children.extend(panels_to_exclude)
    return formatted


def _pop_extra_panels(ar_workspace_data_pb2):
    children = sorted(ar_workspace_data_pb2.children, key=lambda child: child.arLayout.index)
    ignored = children[PANEL_LIMIT:]

    children_to_format = children[:PANEL_LIMIT]
    del ar_workspace_data_pb2.children[:]
    ar_workspace_data_pb2.children.extend(children_to_format)

    return ignored


def _workspace_dimensions(ar_workspace_data_pb2):
    panel_count = min(len(ar_workspace_data_pb2.children), AR_DASHBOARD_PANEL_LIMIT)
    panels_per_row = math.ceil(math.sqrt(panel_count))
    width = panels_per_row * (WorkspaceDimensions.padding + ModelNodeDimensions.width) - WorkspaceDimensions.padding
    return panels_per_row, width


def _set_model_node_positions(ar_workspace_data_pb2, panels_per_row, workspace_width):
    x_translation = (ModelNodeDimensions.width / 2.0) - (workspace_width / 2.0)
    y_translation = (-WorkspaceDimensions.height / 2.0) - (
            ModelNodeDimensions.height / 2.0) - WorkspaceDimensions.padding
    for offset, panel in enumerate(ar_workspace_data_pb2.children):
        x_offset = (offset % panels_per_row) * (ModelNodeDimensions.width + WorkspaceDimensions.padding)
        y_offset = (offset // panels_per_row) * (ModelNodeDimensions.height + WorkspaceDimensions.padding) * -1

        panel.transformMatrix.CopyFrom(_create_transform_matrix(x_translation + x_offset, y_translation + y_offset))
        panel.geometryVector.CopyFrom(_create_geometry_vector(ModelNodeDimensions))


def _set_node_positions(nodes, alignment, dimensions, left_end, right_end):
    if not nodes:
        return left_end, right_end
    x_translation = (left_end - (dimensions.width / 2.0) - WorkspaceDimensions.padding
                     if alignment == Alignment.LEFT else
                     right_end + (dimensions.width / 2.0) + WorkspaceDimensions.padding)
    y_translation = (-WorkspaceDimensions.height / 2.0) - (dimensions.height / 2.0) - WorkspaceDimensions.padding

    height_offset = 0.0
    for node in nodes:
        node.transformMatrix.CopyFrom(_create_transform_matrix(x_translation, y_translation - height_offset))
        node.geometryVector.CopyFrom(_create_geometry_vector(dimensions))
        height_offset += dimensions.height + WorkspaceDimensions.padding

    if alignment == Alignment.LEFT:
        return left_end - (dimensions.width + WorkspaceDimensions.padding), right_end
    return left_end, right_end + dimensions.width + WorkspaceDimensions.padding


def _create_transform_matrix(x_translation, y_translation):
    return Matrix4x4(
        v1=Vector4(x=1.0),
        v2=Vector4(y=1.0),
        v3=Vector4(z=1.0),
        v4=Vector4(x=x_translation, y=y_translation, w=1.0),
    )


def _create_geometry_vector(dimensions):
    return Vector3(
        x=dimensions.width,
        y=dimensions.height,
        z=dimensions.depth,
    )
