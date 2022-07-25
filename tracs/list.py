from dataclasses import fields
from pathlib import Path
from re import match
from re import split

from confuse.exceptions import NotFoundError
from logging import getLogger
from rich import box
from rich.pretty import Pretty as pp
from rich.table import Table

from .activity import Activity
from .config import ApplicationConfig as cfg
from .config import GlobalConfig as gc
from .config import console
from .plugins import Registry
from .utils import fmt
from .utils import red

log = getLogger( __name__ )

FILE_EXISTS = '\u2705' # file has been downloaded
FILE_MISSING = '\u2716' # file is missing (does not exist on server)
FILE_NEEDS_DOWNLOAD = '\u25EF' # file is missing, but might exist on the server
FILE_NEEDS_DOWNLOAD = '\u21A9' # file is missing, but might exist on the server

def list_activities( activities: [Activity], sort: str, format_name: str ) -> None:
	# sort list before printing
	if sort == 'id':
		activities.sort( key=lambda x: x.doc_id )
	elif sort == 'name':
		activities.sort( key=lambda x: x.name )
	elif sort == 'date':
		activities.sort( key=lambda x: x.time )
	elif sort == 'type':
		activities.sort( key=lambda x: x.type )

	try:
		list_format = cfg['formats']['list'][format_name].get()
	except NotFoundError:
		list_format = cfg['formats']['list']['default'].get()
	list_fields = list_format.split()

	headers = []

	for f in list_fields:
		if m := match( '^(\w+)\.(\w+)$', f ):
			headers.append( f'{m.groups()[1].capitalize()} [{m.groups()[0].capitalize()}]' )
		else:
			headers.append( f.capitalize() )

	table = Table( box=box.MINIMAL, show_header=True, show_footer=False )

	table.add_column( '[blue]id' )
	table.add_column( '[blue]name' )
	table.add_column( '[blue]type' )
	table.add_column( '[blue]local time' )
	table.add_column( '[blue]uid' )

	for a in activities:
		table.add_row( pp( a.doc_id ), a.name, fmt( a.type ), fmt( a.localtime ), pp( a.uids ) )

	if len( table.rows ) > 0:
		console.print( table )

def inspect_activities( activities: [Activity], display_table: bool = False ) -> None:
	for a in activities:
		if not display_table:
			table = Table( box=box.MINIMAL, show_header=False, show_footer=False )

			table.add_row( '[blue]field', '[blue]type', '[blue]value' )

			for field, value in a.items():
				if not field.startswith( '_' ):
					table.add_row( field, _type( value ), pp( value ) )

			table.add_row( '[blue]calculated field', '[blue]type', '[blue]value' )
			for key, fn in Activity.get_accessors().items():
				classifier, field = key if type( key ) == tuple else (None, key)
				if classifier is None:
					table.add_row( f'*{field}*', _type( fn( a, a.doc_id ) ), pp( fn( a, a.doc_id ) ) )
				elif classifier == a.classifier:
					table.add_row( field, _type( fn( a, a.doc_id ) ), pp( fn( a, a.doc_id ) ) )

			table.add_row( '[blue]raw field', '[blue]type', '[blue]value' )
			for field, value in a.raw.items():
				table.add_row( field, _type( value ), pp( shorten( value ) ) )

			table.add_row( '[blue]metadata field', '[blue]type', '[blue]value' )
			for field, value in a.metadata.items():
				table.add_row( field, _type( value ), pp( shorten( value ) ) )

			console.print( table )

		else:
			table = Table( box=box.MINIMAL, show_header=True, show_footer=False )
			table.add_column( '[blue]field' )
			table.add_column( '[blue]value' )
			table.add_column( '[blue]lambda()' )
			table.add_column( '[blue]default_lambda()' )
			table.add_column( '[blue]get()' )

			data_dict = {}

			for field, value in a.items():
				if not field.startswith( '_' ):
					# this accesses the field via a[field]
					# data_dict[field] = [None, None, None, value]
					data_dict[field] = [a[field], None, None, a.get( field )]

			for key, fn in Activity.get_accessors().items():
				classifier, field = key if type( key ) == tuple else (None, key)
				if classifier is None:
					if field not in data_dict:
						data_dict[field] = [None, None, None, None]
					data_dict[field][2] = fn( a, a.doc_id )
					data_dict[field][0] = a[field]
				elif classifier == a.classifier:
					if field not in data_dict:
						data_dict[field] = [None, None, None, None]
					data_dict[field][1] = fn( a, a.doc_id )
					data_dict[field][0] = a[field]

			fields = sorted( data_dict.keys() )
			for field in fields:
				_value, _service_value, _base_value, _raw_value = data_dict.get( field )
				if _value or _service_value or _base_value or _raw_value:
					table.add_row( pp( field ), pp( _value ), pp( _service_value ), pp( _base_value ), pp( _raw_value ) )

			console.print( table )

def inspect_registry() -> None:
	console.print( 'Services:' )
	table = Table( box=box.MINIMAL, show_header=True, show_footer=False )
	table.add_column( '[blue]name' )
	table.add_column( '[blue]display name' )
	table.add_column( '[blue]class' )
	table.add_column( '[blue]enabled' )

	for key, value in Registry.services.items():
		table.add_row( value.name, value.display_name, pp( value.__class__ ), pp( value.enabled ) )

	console.print( table )

	console.print( 'Document Classes:' )
	table = Table( box=box.MINIMAL, show_header=True, show_footer=False )
	table.add_column( '[blue]type' )
	table.add_column( '[blue]class' )

	for key, value in Registry.document_classes.items():
		table.add_row( key, pp( f'{value.__module__}.{value.__name__}' ) )

	console.print( table )

	# document handlers

	console.print( 'Document Handlers:' )
	table = Table( box=box.MINIMAL, show_header=True, show_footer=False )
	table.add_column( '[blue]type' )
	table.add_column( '[blue]class' )

	for key, value in Registry.document_handlers.items():
		table.add_row( key, pp( f'{value.__module__}.{value.__name__}' ) )

	console.print( table )

def show_fields():
	for f in fields( Activity ):
		console.print( f'{f.name} <{f.type}>' )

def show_config():
	table = Table( box=box.MINIMAL, show_header=False, show_footer=False )
	table.add_column( justify='left', no_wrap=True )
	table.add_column( justify='left', no_wrap=True )

	table.add_row( 'configuration file', pp( gc.app.cfg_file ) )
	table.add_row( 'state file', pp( gc.app.state_file ) )
	table.add_row( 'library', pp( gc.app.lib_dir ) )
	table.add_row( 'database file', pp( gc.app.db_file ) )
	table.add_row( 'database backup', pp( gc.app.backup_dir ) )

	for s in gc.app.services.values():
		table.add_row( f'{s.display_name} activities:', pp( Path( gc.app.db_dir, s.name ) ) )

	console.print( 'Locations', style='bold' )
	console.print( table )

	console.print( 'Configuration', style='bold' )
	console.print( gc.app.cfg.dump() )

def shorten( s: str ) -> str:
	max_length = 120
	if len( str( s ) ) > max_length:
		start = int( max_length / 2 )
		end = int( len( str( s ) ) - (max_length / 2) )
		return f"{str( s )[:start]}{red('... ...')}{str( s )[end:]}"
	else:
		return s

def _type( o ) -> str:
	s = split( '^<.+\'(.+)\'>$', str( type( o ) ) )
	return s[1] if len( s ) > 2 else str( type( o ) )
