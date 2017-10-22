#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
 MODULE:       i.landsat.import

 AUTHOR(S):    Nikos Alexandris <nik@nikosalexandris.net>
               Based on a python script published in GRASS-Wiki

 PURPOSE:      Import Landsat scenes in independent Mapsets inside GRASS' data
               base

 COPYRIGHT:    (C) 2017 by the GRASS Development Team

               This program is free software under the GNU General Public
               License (>=v2). Read the file COPYING that comes with GRASS
               for details.
"""

#%module
#% description: Imports Landsat scenes (from compressed tar.gz files or unpacked directories)
#% keywords: imagery
#% keywords: landsat
#% keywords: import
#%end

#%flag
#%  key: e
#%  description: External GeoTiFF files as pseudo GRASS raster maps
#%  guisection: Input
#%end

#%flag
#%  key: c
#%  description: Do not copy the metatada file in GRASS' data base
#%  guisection: Input
#%end

#%flag
#%  key: o
#%  description: Override projection check
#%  guisection: Input
#%end

#%flag
#%  key: s
#%  description: Skip import of existing band(s)
#%end

######################
# %rules
# %  excludes: -s, --o
# %end
######################

#%flag
#%  key: r
#%  description: Remove scene directory after import if source is a tar.gz file
#%end

#%flag
#%  key: l
#%  description: List bands and exit
#%  guisection: Input
#%end

#%flag
#%  key: t
#%  description: t.register compliant list of scene names and their timestamp, one per line
#%  guisection: Input
#%end

#%flag
#%  key: f
#%  description: Force time-stamping. Useful for imported bands lacking a timestamp.
#%end

#%rules
#% exclusive: -t, -l
#%end

#%flag
#%  key: n
#%  description: Count scenes in pool
#%  guisection: Input
#%end

#%flag
#%  key: 1
#%  description: Import all scenes in one Mapset
#%  guisection: Optional
#%end

#%option
#% key: scene
#% key_desc: id
#% label: One or multiple Landsat scenes
#% description: Compressed tar.gz files or decompressed and unpacked directories
#% multiple: yes
#% required: no
#%end

#%rules
#% requires_all: -r, scene
#%end

#%option
#% key: pool
#% key_desc: directory
#% label: Directory containing multiple Landsat scenes
#% description: Decompressed and untarred directories
#% multiple: no
#% required: no
#%end

#%rules
#% requires_all: -n, pool
#%end

#%option
#% key: band
#% type: integer
#% required: no
#% multiple: yes
#% description: Input band(s) to select (default is all bands)
#% guisection: Input
#%end

#%option
#% key: mapset
#% key_desc: name
#% label: Mapset to import all scenes in
#% multiple: no
#% required: no
#%end

#%rules
#% collective: -1, mapset
#%end

#%option
#% key: timestamp
#% key_desc: 'yyyy-mm-dd hh:mm:ss.ssssss +zzzz'
#% type: string
#% label: Manual timestamp definition
#% description: Date and time of scene acquisition
#% required: no
#%end

#%option
#%  key: tgis
#%  key_desc: filename
#%  label: Output file name for t.register
#%  description: List of scene names and their timestamp
#%  multiple: no
#%  required: no
#%end

#%option
#%  key: memory
#%  key_desc: Cache
#%  label: Maximum cache memory (in MB) to be used
#%  description: Cache size for raster rows
#%  type: integer
#%  multiple: no
#%  required: no
#%  options: 0-2047
#%  answer: 300
#%end

# required librairies
import os
import sys
import shutil
import tarfile
import glob
# import shlex
import atexit
import grass.script as grass
from grass.exceptions import CalledModuleError
from grass.pygrass.modules.shortcuts import general as g
from grass.pygrass.modules.shortcuts import raster as r

# globals
MONTHS = {'01': 'jan', '02': 'feb', '03': 'mar', '04': 'apr', '05': 'may',
          '06': 'jun', '07': 'jul', '08': 'aug', '09': 'sep', '10': 'oct',
          '11': 'nov', '12': 'dec'}

DATE_STRINGS = ['DATE_ACQUIRED', 'ACQUISITION_DATE']
TIME_STRINGS = ['SCENE_CENTER_TIME', 'SCENE_CENTER_SCAN_TIME']
ZERO_TIMEZONE = '+0000'
GRASS_VERBOSITY_LELVEL_3 = '3'
GEOTIFF_EXTENSION = '.TIF'
IMAGE_QUALITY_STRINGS = ['QA', 'VCID']
QA_STRING = 'QA'
MTL_STRING = 'MTL'
HORIZONTAL_LINE = 79 * '-' + '\n'
MEMORY_DEFAULT = '300'

# environment variables
grass_environment = grass.gisenv()
GISDBASE = grass_environment['GISDBASE']
LOCATION = grass_environment['LOCATION_NAME']
MAPSET = grass_environment['MAPSET']

# # path to "cell_misc"
CELL_MISC = 'cell_misc'

# helper functions
def run(cmd, **kwargs):
    """
    Pass quiet flag to grass commands
    """
    grass.run_command(cmd, quiet=True, **kwargs)

def get_path_to_cell_misc(mapset):
    """
    Return path to the cell_misc directory inside the requested Mapset
    """
    path_to_cell_misc = '/'.join([GISDBASE, LOCATION, mapset, CELL_MISC])
    return path_to_cell_misc

def find_existing_band(band):
    """
    Check if band exists in the current mapset

    Parameter "element": 'raster', 'raster_3d', 'vector'
    """

    result = grass.find_file(name=band, element='cell', mapset='.')
    if result['file']:
        # grass.verbose(_("Band {band} exists".format(band=band)))
        return True

    else:
        return False

def extract_tgz(tgz):
    """
    Decompress and unpack a .tgz file
    """

    g.message(_('Extracting files from tar.gz file'))

    # open tar.gz file in read mode
    tar = tarfile.TarFile.open(name=tgz, mode='r')

    # get the scene's (base)name
    tgz_base = os.path.basename(tgz).split('.tar.gz')[0]

    # try to create a directory with the scene's (base)name
    # source: <http://stackoverflow.com/a/14364249/1172302>
    try:
        os.makedirs(tgz_base)

    # if something went wrong, raise an error
    except OSError:
        if not os.path.isdir(tgz_base):
            raise

    # extract files indide the scene directory
    tar.extractall(path=tgz_base)

def get_name_band(scene, filename):
    """
    """
    absolute_filename = os.path.join(scene, filename)

    # detect image quality strings in filenames
    if any(string in absolute_filename for string in IMAGE_QUALITY_STRINGS):
        name = "".join((os.path.splitext(absolute_filename)[0].split('_'))[1::2])

    # keep only the last part of the filename
    else:
        name = os.path.splitext(filename)[0].split('_')[-1]

    # found a wrongly named *MTL.TIF file in LE71610432005160ASN00
    if MTL_STRING in absolute_filename:  # use grass.warning(_("..."))?
        message_fatal = "Detected an MTL file with the .TIF extension!"
        message_fatal += "\nPlease, rename the extension to .txt and retry."
        grass.fatal(_(message_fatal))

    # is it the QA layer?
    elif (QA_STRING) in absolute_filename:
        band = name

    # is it a two-digit multispectral band?
    elif len(name) == 3 and name[0] == 'B' and name[-1] == '0':
        band = int(name[1:3])

    # what is this for?
    elif len(name) == 3 and name[-1] == '0':
        band = int(name[1:2])

    # what is this for?
    elif len(name) == 3 and name[-1] != '0':
        band = int(name[1:3])

    # is it a single-digit band?
    else:
        band = int(name[-1:])

    # one Mapset requested? prefix raster map names with scene id
    if one_mapset:
        name = os.path.basename(scene) + '_' + name

    return name, band

def get_metafile(scene, tgis):
    """
    Get metadata MTL filename
    """
    metafile = glob.glob(scene + '/*MTL.txt')[0]
    metafile_basename = os.path.basename(metafile)
    scene_basename = os.path.basename(scene)
    return metafile

def is_mtl_in_cell_misc(mapset):
    """
    To implement -- confirm existence of copied MTL in cell_misc instead of
    saying "yes, it's copied" without checking
    """
    cell_misc_directory = get_path_to_cell_misc(mapset)
    globbing = glob.glob(cell_misc_directory + '/' + mapset + '_MTL.txt')

    if not globbing:
        return False

    else:
        return True

def copy_mtl_in_cell_misc(scene, mapset, tgis, copy_mtl=True) :
    """
    Copies the *MTL.txt metadata file in the cell_misc directory inside
    the Landsat scene's independent Mapset or in else the requested single
    Mapset
    """

    if one_mapset:
        mapset = mapset

    path_to_cell_misc = get_path_to_cell_misc(mapset)

    if is_mtl_in_cell_misc(mapset):
        message = HORIZONTAL_LINE
        message += ' MTL exists in {d}\n'.format(d=path_to_cell_misc)
        message += HORIZONTAL_LINE
        g.message(_(message))
        pass

    else:

        if copy_mtl:

            metafile = get_metafile(scene, tgis)

            # copy the metadata file -- Better: check if really copied!
            message = HORIZONTAL_LINE
            message += ' MTL file copied at <{directory}>.'
            message = message.format(directory=path_to_cell_misc)
            g.message(_(message))
            shutil.copy(metafile, path_to_cell_misc)

        else:
            message = HORIZONTAL_LINE
            message += ' MTL not transferred under {m}/cell_misc'.format(m=scene)
            g.message(_(message))

def add_leading_zeroes(real_number, n):
     """
     Add leading zeroes to floating point numbers
     Source: https://stackoverflow.com/a/7407943
     """
     bits = real_number.split('.')
     return '{integer}.{real}'.format(integer=bits[0].zfill(n), real=bits[1])

def get_timestamp(scene, tgis):
    """
    Scope:  Retrieve timestamp of a Landsat scene
    Input:  Metadata *MTL.txt file
    Output: Return date, time and timezone of acquisition
    """

    # if set, get time stamp from options
    if options['timestamp']:
        date_time = options['timestamp']
        timestamp_message = "(set manually)"

    else:

        # get metadata file
        metafile = get_metafile(scene, tgis)

        date_time = dict()

        try:
            metadata = open(metafile)

            for line in metadata.readlines():
                line = line.rstrip('\n')

                if len(line) == 0:
                    continue

                # get Date
                if any(x in line for x in DATE_STRINGS):
                    date_time['date'] = line.strip().split('=')[1].strip()

                # get Time
                if any(x in line for x in TIME_STRINGS):

                    # remove " from detected line
                    if('\"' in line):
                        line = line.replace('\"', '')

                    # first, zero timezone if 'Z' is the last character
                    if line.endswith('Z'):
                        date_time['timezone'] = ZERO_TIMEZONE

                    # remove 'Z' and split the string before & after ':'
                    time = line.strip().split('=')[1].strip().translate(None, 'Z').split(':')

                    # create hours, minutes, seconds in date_time dictionary
                    date_time['hours'] = format(int(time[0]), '02d')
                    date_time['minutes'] = format(int(time[1]), '02d')
                    date_time['seconds'] = add_leading_zeroes(time[2], 2) # float?

        finally:
            metadata.close()

    return date_time

def print_timestamp(scene, timestamp, tgis=False):
    """
    """
    date = timestamp['date']
    hours = str(timestamp['hours'])
    minutes = str(timestamp['minutes'])
    seconds = str(timestamp['seconds'])
    timezone = timestamp['timezone']
    time = ':'.join((hours, minutes, seconds))

    message = 'Date\t\tTime\n\n{date}\t{time} {timezone}\n\n'

    # if -t requested
    if tgis:

        # verbose if -t instructed
        os.environ['GRASS_VERBOSE'] = GRASS_VERBOSITY_LELVEL_3

        # timezone = timezone.replace('+', '')
        message = '{s}<Suffix>|{d} {t} {tz}'.format(s=scene, d=date, t=time, tz=timezone)

    g.message(_(message.format(date=date, time=time, timezone=timezone)))

def set_timestamp(band, timestamp):
    """
    Builds and sets the timestamp (as a string!) for a raster map
    """

    if isinstance(timestamp, dict):

        # year, month, day
        if ('-' in timestamp['date']):
            year, month, day = timestamp['date'].split('-')

        # else, if not ('-' in timestamp['date']): what?

        month = MONTHS[month]

        # assembly
        day_month_year = ' '.join((day, month, year))

        # hours, minutes, seconds
        hours = str(timestamp['hours'])
        minutes = str(timestamp['minutes'])
        seconds = str(timestamp['seconds'])

        # assembly
        hours_minutes_seconds = ':'.join((hours, minutes, seconds))

        # assembly the string
        timestamp = ' '.join((day_month_year, hours_minutes_seconds))
        # timestamp = shlex.quotes(timestamp)  # This is failing in my bash!

    # stamp bands
    run('r.timestamp', map=band, date=timestamp)

def import_geotiffs(scene, mapset, memory, list_bands, tgis = False):
    """
    Imports all bands (GeoTIF format) of a Landsat scene be it Landsat 5,
    7 or 8.  All known naming conventions are respected, such as "VCID" and
    "QA" found in newer Landsat scenes for temperature channels and Quality
    respectively.
    """

    timestamp = get_timestamp(scene, tgis)
    print_timestamp(os.path.basename(scene), timestamp, tgis)

    if not one_mapset:
        # set mapset from scene name
        mapset = os.path.basename(scene)

    message = str()  # a string holder

    # verbosity: target Mapset
    if not any(x for x in (list_bands, tgis)):
        message = 'Target Mapset\t@{mapset}\n\n'.format(mapset=mapset)

    # communicate input band name
    if not tgis:
        message += 'Band\tFilename\n'
        g.message(_(message))

    # loop over files inside a "Landsat" directory
    # sort band numerals, source: https://stackoverflow.com/a/2669523/1172302
    filenames = sorted(os.listdir(scene), key=lambda item:
            (int(item.partition('_B')[2].partition('.')[0])
                if item.partition('_B')[2].partition('.')[0].isdigit()
                else float('inf'), item))
    for filename in filenames:

        # if not GeoTIFF, keep on working
        if os.path.splitext(filename)[-1] != GEOTIFF_EXTENSION:
            continue

        # use the full path name to the file
        name, band = get_name_band(scene, filename)
        band_title = 'band {band}'.format(band = band)

        if not tgis:

            # communicate input band and source file name
            message = '{band}'.format(band = band)
            message += '\t{filename}'.format(filename = filename)
            if not skip_import:
                g.message(_(message))

            else:
                # message for skipping import
                message_skipping = '\t [ Exists, skipping ]'

        if not any(x for x in (list_bands, tgis)):

            # get absolute filename
            absolute_filename = os.path.join(scene, filename)

            parameters = dict(input = absolute_filename,
                    output = name,
                    flags = '',
                    title = band_title,
                    quiet = True)

            if override_projection:
                parameters['flags'] += 'o'

            # if bands:
            #     parameters['band'] = bands

            # create Mapset of interest, if it doesn't exist
            run('g.mapset', flags = 'c', mapset = mapset, stderr = open(os.devnull, 'w'))

            if (skip_import and find_existing_band(name)):

                if force_timestamp:
                    set_timestamp(name, timestamp)
                    g.message(_('   >>> Forced timestamping for {b}'.format(b=name)))

                message_skipping = message + message_skipping
                g.message(_(message_skipping))
                pass

            elif (skip_import and not find_existing_band(name)):
                grass.fatal(_("Skip flag does not apply for new Mapsets"))

            else:

                if link_geotiffs:

                    r.external(**parameters)

                else:
                    if memory:
                        parameters['memory'] = memory
                    # try:
                    r.in_gdal(**parameters)

                    # except CalledModuleError:
                        # grass.fatal(_("Unable to read GDAL dataset {s}".format(s=scene)))

                set_timestamp(name, timestamp)

        else:
            pass

    # copy MTL
    if not list_bands and not tgis:
        copy_mtl_in_cell_misc(scene, mapset, tgis, copy_mtl)

def main():

    global GISDBASE, LOCATION, MAPSET, CELL_MISC, link_geotiffs, copy_mtl, override_projection, skip_import, force_timestamp, one_mapset, mapset

    # flags
    link_geotiffs = flags['e']
    copy_mtl = not flags['c']
    override_projection = flags['o']
    skip_import = flags['s']
    remove_untarred = flags['r']
    list_bands = flags['l']
    count_scenes = flags['n']
    tgis = flags['t']
    force_timestamp = flags['f']
    one_mapset = flags['1']

    # options
    scene = options['scene']
    pool = options['pool']
    timestamp = options['timestamp']
    tregister = options['tgis']
    memory = options['memory']

    if list_bands or count_scenes:  # don't import
        os.environ['GRASS_VERBOSE'] = '3'

    # if a single mapset requested
    if one_mapset:
        mapset = options['mapset']

    else:
        mapset = MAPSET

    if (memory != MEMORY_DEFAULT):
        message = HORIZONTAL_LINE
        message += ('Cache size set to {m} MB\n'.format(m = memory))
        message += HORIZONTAL_LINE
        grass.verbose(_(message))

    # import all scenes from pool
    if pool:
        landsat_scenes = [x[0] for x in os.walk(pool)][1:]

        if count_scenes:
            message = 'Number of scenes in pool: {n}'
            message = message.format(n = len(landsat_scenes))
            g.message(_(message))

        else:
            count = 0
            for landsat_scene in landsat_scenes:
                import_geotiffs(landsat_scene, mapset, memory, list_bands, tgis)

    # import single or multiple given scenes
    if scene:
        landsat_scenes = scene.split(',')

        for landsat_scene in landsat_scenes:
            if 'tar.gz' in landsat_scenes:
                extract_tgz(landsat_scene)
                landsat_scene = landsat_scene.split('.tar.gz')[0]
                message = 'Scene {s} decompressed and unpacked'
                message = message.format(s = scene)
                grass.verbose(_(message))

            import_geotiffs(landsat_scene, mapset, memory, list_bands, tgis)

            if remove_untarred:
                message = 'Removing unpacked source directory {s}'
                message = message.format(s = scene)
                grass.verbose(_(message))
                shutil.rmtree(scene)

            if not tgis and not is_mtl_in_cell_misc(mapset) and (len(landsat_scenes) > 1):
                message = HORIZONTAL_LINE
                g.message(_(message))

if __name__ == "__main__":
    options, flags = grass.parser()
    sys.exit(main())
