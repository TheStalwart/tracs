
from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from dataclasses import Field
from dataclasses import fields
from dataclasses import InitVar
from datetime import datetime, time
from typing import Any
from typing import Callable
from typing import ClassVar
from typing import Dict
from typing import Union

from logging import getLogger
from typing import List
from typing import Optional

from tzlocal import get_localzone_name

from .activity_types import ActivityTypes
from .resources import Resource
from .resources import ResourceGroup
from .utils import fromisoformat
from .utils import sum_times

log = getLogger( __name__ )

@dataclass
class VirtualFields:

	__resolvers__: ClassVar[Dict[str, Callable]] = field( default={} )

	def __getattribute__( self, name: str ) -> Any:
		if name in VirtualFields.__resolvers__.keys():
			return VirtualFields.__resolvers__[name]()
		else:
			return super().__getattribute__( name )

@dataclass
class Activity:

	id: int = field( default=0 )

	classifier: str = field( default=None ) # classifier of this activity, only used in subclasses
	uid: str = field( default=None ) # unique id of this activity in the form of <classifier:number>, only used in subclasses
	uids: List[str] = field( default_factory=list ) # uids of activities which belong to this activity

	raw: Any = field( default=None )  # structured raw data used for initialization from external data
	raw_id: int = field( default=None )  # raw id as raw data might not contain all data necessary
	raw_name: str = field( default=None )  # same as raw id
	raw_data: Union[str, bytes] = field( default=None )  # serialized version of raw, can be i.e. str or bytes

	local_id: int = field( default=None )  # same as raw_id

	name: Optional[str] = field( default=None ) # activity name
	type: Optional[ActivityTypes] = field( default=None ) # activity type
	description: str = field( default=None ) # description
	tags: List[str] = field( default_factory=list ) # list of tags
	equipment: List[str] = field( default_factory=list ) # list of equipment tags

	location_country: Optional[str] = field( default=None ) #
	location_state: Optional[str] = field( default=None ) #
	location_city: Optional[str] = field( default=None ) #
	location_place: Optional[str] = field( default=None ) #
	location_latitude_start: float = field( default=None ) #
	location_longitude_start: float = field( default=None ) #
	location_latitude_end: float = field( default=None ) #
	location_longitude_end: float = field( default=None ) #
	route: str = field( default=None ) #

	time: datetime = field( default=None ) # activity time (UTC)
	time_end: Optional[datetime] = field( default=None ) # activity end time (UTC)
	localtime: datetime = field( default=None ) # activity time (local)
	localtime_end: Optional[datetime] = field( default=None ) # activity end time (local)
	timezone: str = field( default=get_localzone_name() ) # timezone of the activity, local timezone by default
	duration: Optional[time] = field( default=None ) #
	duration_moving: Optional[time] = field( default=None ) #

	distance: Optional[float] = field( default=None ) #
	ascent: Optional[float] = field( default=None ) #
	descent: Optional[float] = field( default=None ) #
	elevation_max: Optional[float] = field( default=None ) #
	elevation_min: Optional[float] = field( default=None ) #
	speed: Optional[float] = field( default=None ) #
	speed_max: Optional[float] = field( default=None ) #

	heartrate: Optional[int] = field( default=None ) #
	heartrate_max: Optional[int] = field( default=None ) #
	heartrate_min: Optional[int] = field( default=None ) #
	calories: Optional[int] = field( default=None ) #

	resources: List[Resource] = field( init=True, default_factory=list )
	parts: List = field( init=True, default_factory=list )

	others: InitVar = field( default=None )
	other_parts: InitVar = field( default=None )
	force: InitVar = field( default=False )

	__dirty__: bool = field( init=False, default=False, repr=False )
	__metadata__: Dict[str, Any] = field( init=False, default_factory=dict )
	__parts__: List[Activity] = field( init=False, default_factory=list, repr=False )
	__resources__: List[Resource] = field( init=False, default_factory=list, repr=False )
	__parent_id__: int = field( init=False, default=0 )

	__vf__: VirtualFields = field( init=False, default=VirtualFields(), hash=False, compare=False )

	@classmethod
	def fields( cls ) -> List[Field]:
		return list( fields( Activity ) )

	@classmethod
	def fieldnames( cls ) -> List[str]:
		return [f.name for f in fields( Activity )]

	@property
	def parent( self ) -> Optional[Activity]:
		return None

	@property
	def parent_ref( self ) -> int:
		return 0

	@property
	def is_multipart( self ) -> bool:
		return False

	@property
	def abbreviated_type( self ) -> str:
		return self.type.abbreviation if self.type else ':question_mark:'

	def __post_init__( self, others: List[Activity], other_parts: List[Activity], force: bool ):
		if self.raw:
			self.__raw_init__( self.raw )
		elif others:
			self.__init_from_others__( others, force )
		elif other_parts:
			self.__init_from_parts__( other_parts, force )

	def __unserialize__( self, f: Optional[Field], k: str, v: Any ) -> Any:
		k = f.name if f else k
		if k == 'type':
			return v if isinstance( v, ActivityTypes ) else ActivityTypes.get( v )
		elif k in [ 'time', 'time_end', 'localtime', 'localtime_end' ]:
			return fromisoformat( v )
		elif k in [ 'duration', 'duration_moving' ]:
			return fromisoformat( v )
		else:
			return v

	def __raw_init__( self, raw: Any ) -> None:
		"""
		Called from __post_init__ with raw data as parameter and can be overridden in subclasses. Will not be called when raw is None.
		:return:
		"""
		pass

	def __init_from_others__( self, others: List[Activity], force: bool ) -> None:
		"""
		Called from __post_init__ with other activities as parameter.

		:return:
		"""
		for f in fields( self ):
			for o in others:
				if value := getattr( o, f.name ):
					if not f.metadata.get( PROTECTED, False ) or force:
						setattr( self, f.name, value ) # todo: make a copy in case of list or dict
					if not force:
						break

	def __init_from_parts__( self, other_parts: List[Activity], force: bool ) -> None:
		"""
		Called from __post_init__ with other activities as parts for this new activity. This method assumes that the list of parts
		is sorted by time already.

		:return:
		"""

		# field selection is currently a manual process ...
		self.time = other_parts[0].time
		self.localtime = other_parts[0].localtime
		self.time_end = other_parts[-1].time_end
		self.localtime_end = other_parts[-1].localtime_end
		self.timezone = other_parts[0].timezone

		self.duration = sum_times( [o.duration for o in other_parts] ) # don't know why pycharm complains about this line
		self.duration_moving = sum_times( [o.duration_moving for o in other_parts] ) # don't know why pycharm complains about this line

		self.distance = s if (s := sum( o.distance for o in other_parts if o.distance )) else None
		self.ascent = s if (s := sum( o.ascent for o in other_parts if o.ascent )) else None
		self.descent = s if (s := sum( o.descent for o in other_parts if o.descent )) else None
		self.elevation_max = max( l ) if ( l := [o.elevation_max for o in other_parts if o.elevation_max is not None] ) else None
		self.elevation_min = min( l ) if ( l := [o.elevation_min for o in other_parts if o.elevation_min is not None] ) else None

		self.speed_max = max( l ) if ( l := [o.speed_max for o in other_parts if o.speed_max is not None] ) else None

		self.heartrate_max = max( l ) if ( l := [o.heartrate_max for o in other_parts if o.heartrate_max is not None] ) else None
		self.heartrate_min = min( l ) if ( l := [o.heartrate_min for o in other_parts if o.heartrate_min is not None] ) else None
		self.calories = s if (s := sum( o.calories for o in other_parts if o.calories )) else None

	def init_from( self, other: Activity = None, raw: Dict = None, force: bool = False ) -> Activity:
		"""
		Initializes this activity with data from another activity/dictionary.

		:param other: other activity
		:param raw: raw data
		:param force: flag to overwrite existing data from other, regardless of existing values (otherwise non-null values will be preferred
		:return: self, for convenience
		"""
		if other:
			for f in fields( self ):
				if not f.metadata.get( PROTECTED, False ):
					other_value = getattr( other, f.name )
					if force:
						setattr( self, f.name, other_value )
					else:
						new_value = getattr( self, f.name ) or other_value
						setattr( self, f.name, new_value )
		elif raw:
			self.raw = raw
			self.__post_init__( serialized_data=None )

		return self

	def tag( self, tag: str ):
		if tag not in self.tags:
			self.tags.append( tag )
			self.tags = sorted( self.tags )

	def untag( self, tag: str ):
		self.tags.remove( tag )

	def resource_group( self ) -> ResourceGroup:
		return ResourceGroup( resources=self.resources )

@dataclass
class MultipartActivity( Activity ):

	parts: List[Activity] = field( default_factory=list, metadata={ 'persist_as': '_parts' } )

#	@property
#	def parts( self ) -> Mapping:
#		return self._access_map( KEY_PARTS )

	@property
	def part_for( self ) -> List[int]:
		return self.parts.get( 'ids', [] )

	@property
	def part_of( self ) -> Optional[int]:
		return self.parts.get( 'parent', None )
