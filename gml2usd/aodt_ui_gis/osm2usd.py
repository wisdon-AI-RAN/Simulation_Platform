import argparse
import sys
import bpy
import addon_utils
import bmesh
import os
import subprocess

def import_osm(minLon, maxLon, minLat, maxLat, export_path):

    bpy.context.scene.blosm.minLon = minLon
    bpy.context.scene.blosm.maxLon = maxLon
    bpy.context.scene.blosm.minLat = minLat
    bpy.context.scene.blosm.maxLat = maxLat

    bpy.context.scene.blosm.highways = False
    bpy.context.scene.blosm.forests = False
    bpy.context.scene.blosm.water = False
    bpy.context.scene.blosm.vegetation = False
    bpy.context.scene.blosm.railways = False
    
    bpy.ops.blosm.import_data()


def clean_up():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='SELECT')

    context = bpy.context
    if (len(context.selected_objects)) <= 3:
        print("the scene contains no objects.")
        exit()
    # This is to make sure that there is an active object in the scene:
    #----------------------------------------------
    if not bpy.context.active_object.hide_viewport:
        for object in bpy.context.scene.objects:
            if not object.hide_viewport:
                bpy.context.view_layer.objects.active = object
                break
        #----------------------------------------------
    bpy.ops.object.join()
    bpy.ops.object.convert(target='MESH') 
    bpy.ops.object.mode_set(mode='EDIT')


    # merge by distance
    bpy.ops.mesh.select_all(action='SELECT')


    bpy.ops.mesh.remove_doubles(threshold = 0.05)
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.mesh.select_mode(type = 'FACE')
    bpy.ops.mesh.select_interior_faces()
    bpy.ops.mesh.delete(type='FACE')

    # fill holes
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.fill_holes(sides=100)

    # triangulate faces
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.quads_convert_to_tris(quad_method='BEAUTY', ngon_method='BEAUTY')  # Convert to Triangles
    bpy.ops.object.mode_set(mode='OBJECT')

    bpy.ops.object.shade_smooth()

    # separate by loose parts
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.separate(type='LOOSE')

    bpy.ops.object.mode_set(mode='OBJECT')

def run(minLon, minLat, maxLon, maxLat, outputFilepath, blender_out, in_usd):

    addon_utils.enable("blosm")

    try:
        import_osm(minLon,maxLon, minLat,maxLat, outputFilepath)
        print(f'File written: {outputFilepath}')
    except:
        print(f'An error occurred with import from OSM.')
        exit()

    print('cleaning up mesh...')
    clean_up()
    
    scratch_blender_file = blender_out
    
    bpy.ops.wm.save_as_mainfile(filepath=scratch_blender_file)


    bpy.ops.wm.usd_export(
                          filepath= in_usd, 
                          check_existing=True, 
                          filter_blender=False, 
                          filter_backup=False,
                          )
    try:
        subprocess.call(f'rm -r {scratch_blender_file}', shell= True)
    except:
        pass


class ArgumentParserForBlender(argparse.ArgumentParser):
    """
    For more information on these classes, see https://blender.stackexchange.com/questions/6817/how-to-pass-command-line-arguments-to-a-blender-python-script/8405#8405.

    This class is identical to its superclass, except for the parse_args
    method (see docstring). It resolves the ambiguity generated when calling
    Blender from the CLI with a python script, and both Blender and the script
    have arguments. E.g., the following call will make Blender crash because
    it will try to process the script's -a and -b flags:
    >>> blender --python my_script.py -a 1 -b 2

    To bypass this issue this class uses the fact that Blender will ignore all
    arguments given after a double-dash ('--'). The approach is that all
    arguments before '--' go to Blender, arguments after go to the script.
    The following calls work fine:
    >>> blender --python my_script.py -- -a 1 -b 2
    >>> blender --python my_script.py --
    """

    def _get_argv_after_doubledash(self):
        try:
            idx = sys.argv.index("--")
            return sys.argv[idx+1:] # the list after '--'
        except ValueError as e: # '--' not in the list:
            return []

    # overrides superclass
    def parse_args(self):
        return super().parse_args(args=self._get_argv_after_doubledash())

if __name__ == "__main__":
    
    parser = ArgumentParserForBlender()

    parser.add_argument("-o", "--output_stage", type=str, required=True)
    parser.add_argument("-c", "--coords", nargs="*", type=float)
    parser.add_argument("-blo", "--blender_out", type=str)
    parser.add_argument("-usd", "--usd_out", type=str)

    args = parser.parse_args()
    
    coords = args.coords
    output_stage = args.output_stage
    blender_out = args.blender_out
    usd_out = args.usd_out

    print(output_stage)

    run(coords[0], coords[1], coords[2], coords[3], output_stage, blender_out, usd_out)
    