
from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime
from inspect import getmembers
from logging import getLogger
from pathlib import Path
from typing import Any
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union

from dateutil.tz import UTC
from fs.base import FS
from fs.multifs import MultiFS
from fs.osfs import OSFS

from .activity import Activity
from .config import ApplicationContext
from .config import DEFAULT_DB_DIR
from .config import GlobalConfig as gc
from .config import KEY_LAST_DOWNLOAD
from .config import KEY_LAST_FETCH
from .config import OVERLAY_DIRNAME
from .db import ActivityDb
from .plugin import Plugin
from .registry import Registry
from .resources import Resource

log = getLogger( __name__ )

@dataclass

# ---- base class for a service ----

class Service( Plugin ):

	def __init__( self, **kwargs ):
		super().__init__( **kwargs )

		# paths + plugin filesystem area
		self._base_path: Path = kwargs.get( 'base_path', Path( DEFAULT_DB_DIR, self.name ) )
		self._overlay_path: Path = kwargs.get( 'overlay_path', Path( self._base_path.parent, OVERLAY_DIRNAME, self.name ) )
		self._base_url = None

		self._fs: MultiFS = MultiFS()
		self._fs.add_fs( 'base', OSFS( str( self._base_path ), create=True ), write=True )
		self._fs.add_fs( 'overlay', OSFS( str( self._overlay_path ), create=True ), write=False )

		self._logged_in: bool = False

		# set service properties from kwargs, if a setter exists
		for p in getmembers( self.__class__, lambda p: type( p ) is property and p.fset is not None ):
			if p[0] in kwargs.keys() and not p[0].startswith( '_' ):
				setattr( self, p[0], kwargs.get( p[0] ) )

		log.debug( f'service instance {self._name} created, with base path = {self._base_path} and overlay_path = {self._overlay_path} ' )

	# properties

	@property
	def logged_in( self ) -> bool:
		return self._logged_in

	@property
	def base_path( self ) -> Path:
		return self._base_path

	@base_path.setter
	def base_path( self, path: Path ) -> None:
		self._base_path = path

	@property
	def overlay_path( self ) -> Path:
		return self._overlay_path

	@overlay_path.setter
	def overlay_path( self, path: Path ) -> None:
		self._overlay_path = path

	@property
	def base_url( self ) -> str:
		return self._base_url

	@base_url.setter
	def base_url( self, url: str ) -> None:
		self._base_url = url

	# todo: still needed?
	@property
	def _db( self ) -> ActivityDb:
		return self.ctx.db

	# fs properties (read-only)

	@property
	def fs( self ) -> FS:
		return self._fs

	@property
	def base_fs( self ) -> FS:
		return self._fs.get_fs( 'base' )

	@property
	def overlay_fs( self ) -> FS:
		return self._fs.get_fs( 'overlay' )

	# class methods for helping with various things

	@classmethod
	def path_for_uid( cls, uid: str ) -> Optional[Path]:
		"""
		Returns the relative path for a given uid.
		A service with the classifier of the uid has to exist, otherwise None will be returned.
		"""
		classifier, local_id = uid.split( ':', 1 )
		if service := Registry.services.get( classifier ):
			return service.path_for_id( local_id, Path( service.name ) )
		else:
			return path_for_id( local_id, Path( classifier ) )

	@classmethod
	def path_for_resource( cls, resource: Resource ) -> Optional[Path]:
		if service := Registry.services.get( resource.classifier ):
			return service.path_for( resource=resource ).resolve()
		else:
			return None

	@classmethod
	def url_for_uid( cls, uid: str ) -> Optional[str]:
		classifier, local_id = uid.split( ':', 1 )
		if service := Registry.services.get( classifier ):
			return service.url_for( local_id=local_id )
		else:
			return None

	@classmethod
	def as_activity( cls, resource: Resource, **kwargs ) -> Optional[Activity]:
		"""
		Loads a resource and transforms it into an activity by using the importer indicated by the resource type.
		"""
		return Registry.importer_for( resource.type ).load_as_activity( Service.path_for_resource( resource ), **kwargs )

	@classmethod
	def as_activity_from( cls, resource: Resource, **kwargs ) -> Optional[Activity]:
		"""
		Loads a resource to an activity in a 'lazy' manner, reusing the existing content of the resource.
		"""
		return Registry.importer_for( resource.type ).load_as_activity( resource=resource, **kwargs )

	# service methods

	def path_for_id( self, local_id: Union[int, str], base_path: Optional[Path] = None, resource_path: Optional[Path] = None ) -> Path:
		return path_for_id( local_id, base_path, resource_path ) # use the default path calculation

	def path_for( self, resource: Resource, ignore_overlay: bool = True, absolute: bool = True, omit_classifier: bool = False ) -> Optional[Path]:
		"""
		Returns the path in the local file system where all artefacts of a provided activity are located.

		:param resource: resource for which the path shall be calculated
		:param ignore_overlay: if True ignores the overlay
		:param absolute: if True returns an absolute path
		:param omit_classifier: if True, the relative path will not include the leading name of the service
		:return: path of the resource in the local file system
		"""
		if resource.classifier == self.name:
			path = Path( self.path_for_id( resource.local_id, base_path=Path( self.name ) ), resource.path )
		else:
			if s := Registry.services.get( resource.classifier ):
				path = s.path_for_id( resource.local_id, Path( resource.classifier ), Path( resource.path ) )
			else:
				return None

		if not absolute and omit_classifier:
			path = path.relative_to( path.parts[0] )

		# return Path( self.base_fs.getsyspath( str( path ) ) ) if absolute else path
		return Path( Path( self.ctx.db_dir_path ), path ) if absolute else path

	def link_for( self, activity: Optional[Activity], resource: Optional[Resource], ext: Optional[str] = None ) -> Optional[Path]:
		ts = activity.time.strftime( '%Y%m%d%H%M%S' )
		path = Path( gc.lib_dir, ts[0:4], ts[4:6], ts[6:8] )
		if resource:
			path = Path( path, f'{ts[8:]}.{self.name}.{resource.type}' )
		elif ext:
			path = Path( path, f'{ts[8:]}.{self.name}.{ext}' )
		return path

	def url_for( self, activity: Optional[Activity] = None, resource: Optional[Resource] = None, local_id: Optional[int] = None ) -> Optional[str]:
		url = None

		if local_id:
			url = self.url_for_id( local_id )
		elif resource and resource.classifier == self.name:
			url = self.url_for_resource_type( resource.local_id, resource.type )
		elif activity:
			try:
				classifier, local_id = activity.uid.split( ':', 1 )
				if classifier == self.name:
					url = self.url_for_id( local_id )
			except KeyError:
				pass

		return url

	@abstractmethod
	def url_for_id( self, local_id: Union[int, str] ) -> str:
		pass

	@abstractmethod
	def url_for_resource_type( self, local_id: Union[int, str], type: str ):
		pass

	# login method

	def login( self ) -> bool:
		pass

	# methods related to fetch()

	def fetch_summary_resources( self, skip: bool, force: bool, pretend: bool, uids: List[str], **kwargs ) -> List[Union[Resource, int]]:
		if skip:
			summaries = self.ctx.db.summaries
		else:
			summaries = self.fetch( force=force, pretend=pretend, **kwargs )  # fetch all summary resources

		if uids:
			summaries = list( filter( lambda s: s.uid in uids, summaries ) )

		# sort summaries by uid so that progress bar in download looks better -> todo: improve progress bar later?
		return sorted( summaries, key=lambda r: r.uid )


	def fetch( self, force: bool, pretend: bool, **kwargs ) -> List[Union[Resource, int]]:
		"""
		This method has to be implemented by a service class. It shall fetch information for
		activities from an external service and return a list of either summary resources or ids.
		This way it can be checked what activities exist and which identifier they have.

		:param force: flag to signal force execution
		:param pretend: pretend flag, do not persist anything
		:param kwargs: additional parameters
		:return: list of fetched summary resources
		"""
		return []

	def fetch_ids( self ) -> List[int]:
		return [ r.local_id for r in self.fetch( force=False, pretend=False ) ]

	# noinspection PyMethodMayBeStatic
	def filter_fetched( self, resources: List[Resource], *uids, **kwargs ) -> List[Resource]:
		# return [r for r in resources if r.uid in uids] if uids else resources
		return [r for r in resources if r.uid in uids]

	# methods related to download()

	def download( self, summary: Resource, force: bool = False, pretend: bool = False, **kwargs ) -> List[Resource]:
		"""
		Downloads related resources like GPX recordings based on a provided activity or summary resource.
		TODO: create a method for all services to ease implementation of subclasses.

		:param summary: summary resource
		:param force: flag force
		:param pretend: pretend flag
		:param kwargs: additional parameters
		:return: a list of downloaded resources
		"""
		return []

	def download_resource( self, resource: Resource, **kwargs ) -> Tuple[Any, int]:
		"""
		Downloads a single resource and returns the content + a status to signal that something has gone wrong.

		:param resource: resource to be downloaded
		:param kwargs: additional parameters
		:return: tuple containing the content + status
		"""
		pass

	def persist_resources( self, resources: List[Resource], force: bool, pretend: bool, **kwargs ) -> None:
		[ self.persist_resource( r, force, pretend, **kwargs ) for r in resources ]

	def persist_resource( self, resource: Resource, force: bool, pretend: bool, **kwargs ) -> None:
		path = self.path_for_resource( resource )
		if not force and path and path.exists():
			return

		try:
			if pretend:
				log.info( f'pretending to write resource {resource.uid}?{resource.path}' )
				return

			if resource.content and len( resource.content ) > 0:
				path.parent.mkdir( parents=True, exist_ok=True )
				path.write_bytes( resource.content )
				self.ctx.db.upsert_resource( resource )

		except TypeError:
			log.error( f'error writing resource data for resource {resource.uid}?{resource.path}', exc_info=True )

	# noinspection PyMethodMayBeStatic
	def postprocess_summaries( self, resources: List[Resource], **kwargs ) -> List[Resource]:
		return resources

	# noinspection PyMethodMayBeStatic
	def postprocess_downloaded( self, resources: List[Resource], **kwargs ) -> List[Resource]:
		return resources

	def postprocess_resources( self, resources: List[Resource], **kwargs ) -> None:
		[ self.postprocess_resource( resource, **kwargs ) for resource in resources ]

	def postprocess_resource( self, resource: Resource = None, **kwargs ) -> None:
		pass

	# noinspection PyMethodMayBeStatic,PyUnresolvedReferences
	def create_activities( self, summary: Resource, resources: List[Resource], **kwargs ) -> List[Activity]:
		return [ Service.as_activity_from( summary ) ]

	# noinspection PyMethodMayBeStatic
	def postprocess_activities( self, activities: List[Activity], resources: List[Resource], **kwargs ) -> List[Activity]:
		"""
		Postprocesses activities after they have been created, by default nothing is done.

		:param activities: activities to postprocess
		:param resources: associated resources, belonging to the provided activities
		:return: postprocessed activities
		"""
		return activities

	def persist_activities( self, activities: List[Activity], force: bool, pretend: bool, **kwargs ) -> None:
		[ self._db.upsert_activity( a ) for a in activities ]

	def import_activities( self, force: bool = False, pretend: bool = False, **kwargs ):
		skip_fetch = kwargs.get( 'skip_fetch', False )
		skip_download = kwargs.get( 'skip_download', False )
		skip_link = kwargs.get( 'skip_link', False )
		uids: List[str] = kwargs.get( 'uids', [] )

		# start fetch task
		self.ctx.start( f'fetching activity data from {self.display_name}' )

		# fetch summaries
		summaries = self.fetch_summary_resources( skip_fetch, force, pretend, **{'uids': uids, **kwargs} )
		summaries = self.postprocess_summaries( summaries, **kwargs )  # post process summaries

		# filter out summaries that are already known
		if not force:
			summaries = [s for s in summaries if not self.ctx.db.contains_resource( s.uid, s.path )]

		# mark task as done
		self.set_state_value( KEY_LAST_FETCH, datetime.utcnow().astimezone( UTC ).isoformat() ) # update fetch timestamp
		self.ctx.complete( 'done' )

		# download resources

		self.ctx.start( f'downloading activity data from {self.display_name}', len( summaries ) )

		while summaries:
			# download resources for summary
			summary = summaries.pop()
			self.ctx.advance( f'{summary.uid}' )

			downloaded_resources = self.download( summary=summary, force=force, pretend=pretend, **kwargs ) if not skip_download else []
			downloaded_resources = self.postprocess_downloaded( downloaded_resources, **kwargs )  # post process
			resources = [summary, *downloaded_resources]

			# persist all resources
			self.persist_resources( resources, force=force, pretend=pretend, **kwargs )

			# create activity/activities from downloaded resources
			activities = self.create_activities( summary=summary, resources=resources, **kwargs )
			activities = self.postprocess_activities( activities, resources, **kwargs )

			# persist activities
			self.persist_activities( activities, force=force, pretend=pretend, **kwargs )

		# mark download task as done
		self._db.commit()
		self.set_state_value( KEY_LAST_DOWNLOAD, datetime.utcnow().astimezone( UTC ).isoformat() )  # update download timestamp
		self.ctx.complete( 'done' )

		# link / vfs

		if not skip_link:
			pass # not yet implemented

	def link( self, activity: Activity, resource: Resource, force: bool, pretend: bool ) -> None:
		if resource.type in ['gpx', 'tcx'] and resource.status == 200: # todo: make linkable resources configurable
			src = self.path_for( resource=resource )
			dest = self.link_for( activity, resource )

			if not src or not dest:
				log.error( f"cannot determine source and/or destination for linking activity {activity.id}" )
				return

			if not src.exists() or src.is_dir():
				log.error( f"cannot link activity {activity.id}: source file {src} does not exist or is not a file" )
				return

			if not pretend:
				dest.parent.mkdir( parents=True, exist_ok=True )
				dest.unlink( missing_ok=True )
				dest.symlink_to( src )

			log.debug( f"linked resource for activity {activity.id}: {src} -> {dest}" )

	def setup( self, ctx: ApplicationContext ) -> None:
		pass

# helper functions

def path_for_id( local_id: Union[int, str], base_path: Optional[Path] = None, resource_path: Optional[Path] = None ) -> Path:
	local_id_rjust = str( local_id ).rjust( 3, '0' )
	path = Path( f'{local_id_rjust[0]}/{local_id_rjust[1]}/{local_id_rjust[2]}/{local_id}' )
	path = Path( base_path, path ) if base_path else path
	path = Path( path, resource_path ) if resource_path else path
	return path
