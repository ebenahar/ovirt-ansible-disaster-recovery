#!/usr/bin/python
from bcolors import bcolors

try:
    import configparser
except ImportError:
    import ConfigParser as configparser
import os.path
import shlex
import subprocess
import sys

from subprocess import call

INFO = bcolors.OKGREEN
INPUT = bcolors.OKGREEN
WARN = bcolors.WARNING
FAIL = bcolors.FAIL
END = bcolors.ENDC
PREFIX = "[Generate Mapping File] "
CA_DEF = '/etc/pki/ovirt-engine/ca.pem'
USERNAME_DEF = 'admin@internal'
SITE_DEF = 'http://127.0.0.1:8080/ovirt-engine/api'
VAR_DEF = "/var/lib/ovirt-ansible-disaster-recovery/mapping_vars.yml"
PLAY_DEF = "../examples/dr_play.yml"


class GenerateMappingFile():

    def run(self, conf_file, log_file):
        print("\n%s%sStart generate variable mapping file "
              "for oVirt ansible disaster recovery%s"
              % (INFO,
                 PREFIX,
                 END))
        dr_tag = "generate_mapping"
        site, username, password, ca_file, var_file_path, _ansible_play = \
            self._init_vars(conf_file)
        print("\n%s%sSite address: %s \n"
              "%susername: %s \n"
              "%spassword: *******\n"
              "%sca file location: %s \n"
              "%soutput file location: %s \n"
              "%sansible play location: %s \n%s"
              % (INFO,
                 PREFIX,
                 site,
                 PREFIX,
                 username,
                 PREFIX,
                 PREFIX,
                 ca_file,
                 PREFIX,
                 var_file_path,
                 PREFIX,
                 _ansible_play,
                 END))
        if not self._validate_connection(site, username, password, ca_file):
            self._print_error(log_file)
            exit()
        command = "site=" + site + " username=" + username + " password=" + \
            password + " ca=" + ca_file + " var_file=" + var_file_path
        cmd = []
        cmd.append("ansible-playbook")
        cmd.append(_ansible_play)
        cmd.append("-t")
        cmd.append(dr_tag)
        cmd.append("-e")
        cmd.append(command)
        cmd.append("-vvv")
        with open(log_file, "w") as f:
            call(cmd, stdout=f)
        if not os.path.isfile(var_file_path):
            self._print_error(log_file)
            exit()
        print("\n%s%sVar file location: '%s'%s"
              % (INFO,
                 PREFIX,
                 var_file_path,
                 END))
        self._print_success()

    def _print_success(self):
        print("%s%sFinished generating variable mapping file "
              "for oVirt ansible disaster recovery%s"
              % (INFO,
                 PREFIX,
                 END))

    def _print_error(self, log_file):
        print("%s%sFailed to generate var file."
              " See log file '%s' for further details%s"
              % (FAIL,
                 PREFIX,
                 log_file,
                 END))

    def _validate_connection(self,
                             url,
                             username,
                             password,
                             ca):
        conn = None
        try:
            conn = self._connect_sdk(url,
                                     username,
                                     primary_password,
                                     primary_ca)
            dcs_service = conn.system_service().data_centers_service()
            dcs_service.list()
        except Exception:
            print(
                "%s%sConnection to setup has failed."
                " Please check your cradentials: "
                "\n%s URL: %s"
                "\n%s USER: %s"
                "\n%s CA file: %s%s" %
                (FAIL,
                 PREFIX,
                 PREFIX,
                 url,
                 PREFIX,
                 username,
                 PREFIX,
                 ca,
                 END))
            if conn:
                conn.close()
            return False
        return True

    def _validate_output_file_exists(self, fname):
        _dir = os.path.dirname(fname)
        if not os.path.exists(_dir):
            print("%s%sPath %s does not exists. Create folder%s"
                  % (WARN,
                     PREFIX,
                     _dir,
                     END))
            os.makedirs(_dir)
        if os.path.isfile(fname):
            valid = {"yes": True, "y": True, "ye": True,
                     "no": False, "n": False}
            ans = raw_input("%s%sThe output file '%s' "
                            "already exists. "
                            "Would you like to override it (y,n)?%s "
                            % (INPUT,
                               PREFIX,
                               fname,
                               END))
            while True:
                ans = ans.lower()
                if ans in valid:
                    if not valid[ans]:
                        print("%s%sFailed to create output file. "
                              "File could not be overriden.%s"
                              % (WARN,
                                 PREFIX,
                                 END))
                        sys.exit(0)
                    break
                else:
                    ans = raw_input("%s%sPlease respond with 'yes' or 'no': %s"
                                    % (INPUT,
                                       PREFIX,
                                       END))
            try:
                os.remove(fname)
            except OSError:
                print("\n\n%s%SFile %s could not be replaced.%s"
                      % (WARN,
                         PREFIX,
                         fname,
                         END))
                sys.exit(0)

    def _init_vars(self, conf_file):
        """ Declare constants """
        _SECTION = "generate_vars"
        _SITE = 'site'
        _USERNAME = 'username'
        _PASSWORD = 'password'
        _CA_FILE = 'ca_file'
        _OUTPUT_FILE = 'output_file'
        _ANSIBLE_PLAY = 'ansible_play'

        """ Declare varialbles """
        site, username, password, ca_file, output_file, ansible_play = '', \
            '', '', '', '', ''
        settings = configparser.ConfigParser()
        settings._interpolation = configparser.ExtendedInterpolation()
        settings.read(conf_file)
        site = settings.get(_SECTION, _SITE,
                            vars=DefaultOption(settings,
                                               _SECTION,
                                               site=None))
        username = settings.get(_SECTION, _USERNAME,
                                vars=DefaultOption(settings,
                                                   _SECTION,
                                                   username=None))
        password = settings.get(_SECTION, _PASSWORD,
                                vars=DefaultOption(settings,
                                                   _SECTION,
                                                   password=None))
        ca_file = settings.get(_SECTION, _CA_FILE,
                               vars=DefaultOption(settings,
                                                  _SECTION,
                                                  ca_file=None))
        output_file = settings.get(_SECTION, _OUTPUT_FILE,
                                   vars=DefaultOption(settings,
                                                      _SECTION,
                                                      output_file=None))
        ansible_play = settings.get(_SECTION, _ANSIBLE_PLAY,
                                    vars=DefaultOption(settings,
                                                       _SECTION,
                                                       ansible_play=None))
        if (not site):
            site = raw_input("%s%sSite address is not initialized. "
                             "Please provide the site URL (%s):%s "
                             % (INPUT,
                                PREFIX,
                                SITE_DEF,
                                END)) or SITE_DEF
        if (not username):
            username = raw_input("%s%sUsername is not initialized. "
                                 "Please provide username "
                                 "(%s):%s "
                                 % (INPUT,
                                    PREFIX,
                                    USERNAME_DEF,
                                    END)) or USERNAME_DEF
        while (not password):
            password = raw_input("%s%sPassword is not initialized. "
                                 "Please provide the password for "
                                 "username %s:%s "
                                 % (INPUT,
                                    PREFIX,
                                    username,
                                    END))

        while (not ca_file):
            ca_file = raw_input("%s%sCa file is not initialized. "
                                "Please provide the ca file location "
                                "(%s):%s "
                                % (INPUT,
                                    PREFIX,
                                    CA_DEF,
                                    END)) or CA_DEF

        while (not output_file):
            output_file = raw_input("%s%sOutput file is not initialized. "
                                    "Please provide the output file location "
                                    "for the mapping var file (%s):%s "
                                    % (INPUT,
                                        PREFIX,
                                        VAR_FILE,
                                        END)) or VAR_FILE
        self._validate_output_file_exists(output_file)
        while (not ansible_play) or (not os.path.isfile(ansible_play)):
            ansible_play = raw_input("%s%sAnsible play '%s' is not "
                                     "initialized. Please provide the ansible "
                                     "play to generate the mapping var file "
                                     "(%s):%s "
                                     % (INPUT,
                                        PREFIX,
                                        ansible_play,
                                        PLAY_DEF,
                                        END)) or PLAY_DEF
        return (site, username, password, ca_file, output_file, ansible_play)


class DefaultOption(dict):

    def __init__(self, config, section, **kv):
        self._config = config
        self._section = section
        dict.__init__(self, **kv)

    def items(self):
        _items = []
        for option in self:
            if not self._config.has_option(self._section, option):
                _items.append((option, self[option]))
            else:
                value_in_config = self._config.get(self._section, option)
                _items.append((option, value_in_config))
        return _items


if __name__ == "__main__":
    GenerateMappingFile().run('dr.conf', '/var/log/ovirt-dr/ovirt-dr.log')
