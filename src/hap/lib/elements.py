"""
A module to define the classes for the elements of the HAP model.

Classes:
    Segment: A class to represent a segment of the HAP model.
    Region: A class to represent a region of the HAP model.
"""

from typing import Any


class Segment:
    """
    A class to represent a segment of the HAP model.
    """

    def __init__(self, id: str, original=True):
        """
        Initialize the segment with the given ID.

        Args:
            id (str): The ID of the segment.
            original (bool): If the segment is build from a true node in the
            graph, rather than a wrapper or a compensate.

        Returns:
            Segment: The initialized segment.
        """

        # Identifiers
        self.id = id
        self.original_id = id if original else None
        self.semantic_id = None

        # Indexing properties
        self.level_range = [0, 0]
        self.coordinate = [0, 0]
        self.rank = 0

        # Statistics
        self.length = 0
        self.frequency = 0
        self.direct_variants = 0
        self.total_variants = 0
        self.is_wrapper = False

        # No sequence stored for performance reasons
        # self.sequence = None

        # Relations
        # self.region = None
        self.sub_regions: list[str] = []
        self.sources: list[str] = []
        # self.source_coordinates: dict[str, list[int]] = {}  # Optional, currently muted

    def to_dict(self) -> dict[str, Any]:
        """
        Return the segment attributes as a dictionary.

        Returns:
            dict: The segment attributes as a dictionary.
        """
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


class Region:
    """
    A class to represent a region of the HAP model.
    """

    def __init__(self, id: str, type: str):
        """
        Initialize the region with the given ID and type.

        Args:
            id (str): The ID of the region.
            type (str): The type of the region.

        Returns:
            Region: The initialized region.
        """

        # Identifiers
        self.id = id
        self.semantic_id = None

        # Indexing properties
        self.level_range = [0, 0]
        self.coordinate = [0, 0]
        self.is_default = False

        # Statistics
        self.length = 0
        self.is_variant = True if type == "var" or type != "con" else False
        self.type = type
        self.total_variants = 0

        # Relations
        self.subgraph = None
        self.parent_segment = None
        self.segments: list[str] = []

        # Utilities
        self.sources: list[str] = []
        self.min_length = 0
        self.before = None
        self.after = None

    def add_segment(self, id: str):
        """
        Create and add segment to current region, setting the same
        `level_range`, `sources`, and return the created segment.
        If region `type` is `con` and no segment exists, added segment
        is set to default.

        Args:
            id (str): The ID of the segment to be added.

        Returns:
            Segment: The added segment.
        """

        segment = Segment(id)
        self.segments.append(segment.id)
        segment.level_range = self.level_range
        segment.sources = self.sources
        return segment

    def to_dict(self) -> dict[str, Any]:
        """
        Return the region attributes as a dictionary.

        Returns:
            dict: The region attributes as a dictionary.
        """
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    def from_dict(self, dict: dict[str, Any]):
        """
        Update the region attributes from a dictionary.

        Args:
            dict (dict): The dictionary with the new values.
        """
        for k, v in dict.items():
            if hasattr(self, k) and not k.startswith("_"):
                setattr(self, k, v)
