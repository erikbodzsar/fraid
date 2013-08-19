#!/usr/bin/python
"""
fraid utility to create virtual disks
that are distributed on multiple physical disks.
"""

from os import listdir, path, mkdir, access, F_OK, devnull, remove
from subprocess import check_output, PIPE, Popen
from re import match

try:
    check_output(["mdadm" ,"--help"])
except OSError:
    print "mdadm package must be installed!"
    quit()

CONFIG_DIR = "/etc/fraid"
if not access(CONFIG_DIR, F_OK):
    mkdir(CONFIG_DIR)
check_output(["modprobe", "loop"])
DEV_NULL = open(devnull, "w")

def usage():
    """
    Prints usage info.
    """
    print "Commands:"
    print "  list : list current fraids"
    print  \
        "  create name size dirs... : create a new fraid called name,\n" + \
        " "*29 + "with a per-file capacity of size GB,\n" + \
        " "*29 + "storing files in the directories specified by dirs"
    print "  up name : create the device /dev/md/name for fraid name"
    print "  down name : remote the md and loop devices corresponding to name"
    print "  delete name : delete the files and metadata of fraid name"
    print "  quit : quit fraid"


def get_loops():
    """
    Returns a dictionary that maps files to loop devices.
    """
    def parse_loop_dev(line):
        """
        Parses a losetup -a output line into a (file, loopdevice) tuple.
        """
        end_of_dev = line.find(':')
        start_of_file = line.rfind('(')
        return (line[start_of_file+1:-1], line[0:end_of_dev])
    return dict(map(parse_loop_dev,
                    check_output(["losetup", "-a"]).splitlines()))


def create_loops(filenames):
    """
    Create or identifies loop devices corresponding to files.
    Returns a list of the loop devices.
    """
    current = get_loops()
    def create_loop(filename):
        """
        Creates or identifies a loop device corresponding to a file.
        """
        if file in current:
            return current[filename]
        else:
            return check_output(["losetup", "-f", "--show", filename]).rstrip()
    return map(create_loop, filenames)


def read_dirs_from_config(config):
    """
    Returns a list of the directories of a fraid.
    """
    return open(CONFIG_DIR+"/"+config, "r").read().splitlines()


def read_files_from_config(name):
    """
    Returns a list of the files of a fraid.
    """
    return [d+"/"+name+".fdisk" for d in read_dirs_from_config(name)]


def active_mds():
    """
    Returns a list of the active mds.
    """
    try:
        return listdir("/dev/md")
    except:
        return []


def current_fraids():
    """
    Returns a list of the created fraids.
    """
    return listdir(CONFIG_DIR)


def fraid_exists(name):
    """
    Checks if a fraid already exists.
    """
    return name in current_fraids()


def activate_fraid(name):
    """
    Create necessary loops for a fraid and then create the md device.
    """
    loops = create_loops(read_files_from_config(name))
    mdproc = Popen(["mdadm", "--create", "/dev/md/"+name,
                    "--level=0", "--raid-devices="+str(len(loops))] + loops,
                   stdin=PIPE, stdout=DEV_NULL, stderr=DEV_NULL)
    mdproc.communicate("y")
    mdproc.wait()
    print "device for fraid", name, "created at /dev/md/"+name


def ask_user(question):
    """
    Ask user a yes/no question and return answer as a boolean.
    """
    while True:
        ans = raw_input(question + " [y/n] ")
        if ans == "y" or ans == "n":
            return ans == "y"


def create_fraid(name, size, dirs):
    """
    Create metadata and files for fraid name.
    """
    def create_file_bg(directory):
        """
        Create the fraid file in a background process.
        """
        return Popen(
            ["dd", "if=/dev/zero", "of="+directory+"/"+name+".fdisk",
             "bs=1G", "count="+str(size)], stderr=DEV_NULL)
    with open(CONFIG_DIR+"/"+name, "w") as fraidfile:
        for directory in dirs:
            fraidfile.write(directory+"\n")
    for proc in map(create_file_bg, dirs):
        proc.wait()


def main():
    """
    Command handling loop.
    """
    while True:
        cmds = raw_input("> ").rstrip().split(" ")
        cmd = cmds[0]
        args = cmds[1:]
        if cmd == "quit":
            break
    
        elif cmd == "list":
            active = set(active_mds())
            for fraid in current_fraids():
                files = read_files_from_config(fraid)
                print fraid, "[ACTIVE]" if fraid in active else "[INACTIVE]", \
                    path.getsize(files[0])*len(files)/pow(10, 9), "GB"
                for filename in files:
                    print "  ", filename
                
        elif cmd == "up":
            name = args[0]
            if name in active_mds():
                print name, "is already active!"
                continue
            activate_fraid(name)
        
        elif cmd == "down":
            name = args[0]
            if not name in current_fraids():
                print name, "is not a fraid!"
                continue
            if not name in active_mds():
                print name, "is not active!"
                continue
            check_output(["mdadm", "--stop", "/dev/md/"+name], stderr=DEV_NULL)
            loops = get_loops()
            for dev in [loops[f] for f in read_files_from_config(name)]:
                check_output(["losetup", "-d", dev])
            
        elif cmd == "create":
            if len(args) < 3:
                print "Usage: create size dirs..."
                continue
            name = args[0]
            if not match(r'^[A-Za-z0-9_]+$', name):
                print name, "is not a valid fraid name! " \
                    "Please only use alphanumerics and underscores."
                continue
            if fraid_exists(name):
                print name, "already exists!"
                continue
            size = 0
            if args[1].isdigit() and int(args[1]) > 0:
                size = int(args[1])
            else:
                print "size (" + args[1] + ") is not a positive integer!"
                continue
            dirs = args[2:]
            if len(dirs) != len(set(dirs)):
                print "directory list has duplicates!"
                continue
            create_fraid(name, size, dirs)
            activate_fraid(name)

        elif cmd == "delete":
            name = args[0]
            if not fraid_exists(name):
                print name, "doesn't exist!"
                continue
            if name in active_mds():
                print name, "is active! do down", name, "first!"
                continue
            if ask_user("Are you sure you want to delete " + name + \
                " and ALL corresponding files?"):
                for filename in read_files_from_config(name):
                    remove(filename)
                remove(CONFIG_DIR+"/"+name)

        else:
            usage()

if __name__ == "__main__":
    main()
