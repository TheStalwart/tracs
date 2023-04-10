
from csv import field_size_limit
from csv import reader as csv_reader
from typing import Any
from typing import Optional
from typing import Type

from orjson import loads as load_json
from orjson import dumps as save_json
from orjson import OPT_APPEND_NEWLINE
from orjson import OPT_INDENT_2
from orjson import OPT_SORT_KEYS

from ..registry import importer
from ..handlers import ResourceHandler
from ..resources import Resource

CSV_TYPE = 'text/csv'
JSON_TYPE = 'application/json'
XML_TYPE = 'application/xml'
TCX_TYPE = 'application/tcx+xml'

@importer( type=CSV_TYPE )
class CSVHandler( ResourceHandler ):

	def __init__( self, resource_type: Optional[str] = None, activity_cls: Optional[Type] = None, **kwargs ) -> None:
		super().__init__( resource_type=resource_type or CSV_TYPE, activity_cls=activity_cls )
		self.field_size_limit = kwargs.get( 'field_size_limit', 131072 ) # keep this later use

	def load_data( self, resource: Resource, **kwargs ) -> None:
		resource.raw = [ r for r in csv_reader( self.as_str( resource.content ).splitlines() ) ]

	@property
	def field_size_limit( self ) -> int:
		return self._field_size_limit

	@field_size_limit.setter
	def field_size_limit( self, limit: int ) -> None:
		self._field_size_limit = limit
		field_size_limit( self._field_size_limit )

@importer( type=JSON_TYPE )
class JSONHandler( ResourceHandler ):

	options = OPT_APPEND_NEWLINE | OPT_INDENT_2 | OPT_SORT_KEYS

	def __init__( self, resource_type: Optional[str] = None, activity_cls: Optional[Type] = None ) -> None:
		super().__init__( resource_type=resource_type or JSON_TYPE, activity_cls=activity_cls )

	def load_data( self, resource: Resource, **kwargs ) -> None:
		resource.raw = load_json( resource.content )

	def save_data( self, data: Any, **kwargs ) -> bytes:
		return save_json( data, option=JSONHandler.options )
