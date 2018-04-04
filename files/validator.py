#!/usr/bin/python
from ansible_vault import Vault
from bcolors import bcolors
try:
    import configparser
except ImportError:
    import ConfigParser as configparser
import os.path
import ovirtsdk4 as sdk
import ovirtsdk4.types as types
import shlex
from subprocess import call
import sys
import yaml

INFO = bcolors.OKGREEN
INPUT = bcolors.OKGREEN
WARN = bcolors.WARNING
FAIL = bcolors.FAIL
END = bcolors.ENDC
PREFIX = "[Validate Mapping File] "


class ValidateMappingFile():

    def_var_file = "/var/lib/ovirt-ansible-disaster-" \
                   "recovery/mapping_vars.yml"
    def_vault = "/var/lib/ovirt-ansible-disaster-" \
                "recovery/passwords.yml"
    var_file = ""
    vault = ""
    cluster_map = 'dr_cluster_mappings'
    domain_map = 'dr_import_storages'
    role_map = 'dr_role_mappings'
    aff_group_map = 'dr_affinity_group_mappings'
    aff_label_map = 'dr_affinity_label_mappings'

    def run(self, conf_file, log_file):
        print("%s%sValidate variable mapping file "
              "for oVirt ansible disaster recovery%s"
              % (INFO,
                 PREFIX,
                 END))
        self._set_dr_conf_variables(conf_file)
        print("%s%sVar File: '%s'%s"
              % (INFO,
                 PREFIX,
                 self.var_file,
                 END))
        if not os.path.isfile(self.var_file):
            print("%s%sVar file '%s' does not exist%s"
                  % (FAIL,
                     PREFIX,
                     self.var_file,
                     END))
            exit()

        python_vars = self._read_var_file()
        vault_password = raw_input(
            "%s%sPlease provide vault password for file '%s':\n"
            "(for plain file, press the enter key): %s" %
            (INPUT,
             PREFIX,
             self.vault_file,
             END))
        if (not self._validate_duplicate_keys(python_vars) or not
                self._entity_validator(python_vars, vault_password)):
            self._print_finish_error()
            exit()

        if (not self._validate_hosted_engine(python_vars)):
            self._print_finish_error()
            exit()
        self._print_finish_success()

    def _print_finish_error(self):
        print("%s%sFailed to validate variable mapping file "
              "for oVirt ansible disaster recovery%s"
              % (FAIL,
                 PREFIX,
                 END))

    def _print_finish_success(self):
        print("%s%sFinished validation variable mapping file "
              "for oVirt ansible disaster recovery%s"
              % (INFO,
                 PREFIX,
                 END))

    def _read_var_file(self):
        with open(self.var_file, 'r') as info:
            info_dict = yaml.load(info)
        return info_dict

    def _set_dr_conf_variables(self, conf_file):
        # Get default location of the yml var file.
        settings = configparser.ConfigParser()
        settings._interpolation = configparser.ExtendedInterpolation()
        settings.read(conf_file)
        var_file = settings.get('validate_vars', 'var_file',
                                vars=DefaultOption(settings,
                                                   'validate_vars',
                                                   site=self.def_var_file))

        # If no default location exists, get the location from the user.
        while not var_file:
            var_file = raw_input(PREFIX + "Var file is not initialized. "
                                 "Please provide the location of the var file "
                                 "(" + self.def_var_file + ")" or def_var_file)

        vault_file = settings.get(
            'validate_vars',
            'vault',
            vars=DefaultOption(
                settings,
                'validate_vars',
                site=self.def_vault))

        # If no default location exists, get the location from the user.
        while (not vault_file):
            vault_file = raw_input(
                PREFIX + "Passwords file is not initialized. "
                "Please provide the location of the passwords file "
                "(" + self.def_vault_file + ")" or def_vault_file)

        self.var_file = var_file
        self.vault_file = vault_file

    def _print_duplicate_keys(self, duplicates, keys):
        ret_val = False
        for key in keys:
            if len(duplicates[key]) > 0:
                print(
                    "%s%sFound the following duplicate keys "
                    "in %s: %s%s" %
                    (FAIL,
                     PREFIX,
                     key,
                     list(duplicates[key]),
                     END))
                ret_val = True
        return ret_val

    def _entity_validator(self, python_vars, vault_password):
        isValid = True
        ovirt_setups = ConnectSDK(
            python_vars,
            self.vault_file,
            vault_password)
        isValid = ovirt_setups.validate_primary() and isValid
        isValid = ovirt_setups.validate_secondary() and isValid
        if isValid:
            try:
                primary_conn, second_conn = '', ''
                primary_conn = ovirt_setups.connect_primary()
                if primary_conn is None:
                    return False
                isValid = self._validate_entities_in_setup(
                    primary_conn, 'primary', python_vars) and isValid
                primary_conn.close()
                second_conn = ovirt_setups.connect_secondary()
                if second_conn is None:
                    return False
                isValid = self._validate_entities_in_setup(
                    second_conn, 'secondary', python_vars) and isValid
            finally:
                # Close the connections
                if primary_conn:
                    primary_conn.close()
                if second_conn:
                    second_conn.close()

        self._is_compatible_versions(
            ovirt_setups, python_vars.get(
                self.cluster_map))
        return isValid

    def _validate_entities_in_setup(self, conn, setup, python_vars):
        isValid = True
        dcs_service = conn.system_service().data_centers_service()
        dcs_list = dcs_service.list()
        clusters = []
        affinity_groups = set()
        for dc in dcs_list:
            dc_service = dcs_service.data_center_service(dc.id)
            clusters_service = dc_service.clusters_service()
            attached_clusters_list = clusters_service.list()
            for cluster in attached_clusters_list:
                clusters.append(cluster.name)
                cluster_service = clusters_service.cluster_service(cluster.id)
                affinity_groups.update(
                    self._fetch_affinity_groups(cluster_service))
        aff_labels = self._get_affinity_labels(conn)
        aaa_domains = self._get_aaa_domains(conn)
        # TODO: Remove  once vnic prifle is validated.
        # _get_vnic_profile_mapping(conn)
        isValid = self._validate_entity_exists(
            clusters, python_vars, self.cluster_map, setup) and isValid
        isValid = self._validate_entity_exists(
            list(affinity_groups),
            python_vars,
            self.aff_group_map,
            setup) and isValid
        isValid = self._validate_entity_exists(
            aff_labels, python_vars, self.aff_label_map, setup) and isValid
        return isValid

    def _fetch_affinity_groups(self, cluster_service):
        affinity_groups = set()
        affinity_groups_service = cluster_service.affinity_groups_service()
        for affinity_group in affinity_groups_service.list():
            affinity_groups.add(affinity_group.name)
        return list(affinity_groups)

    def _get_affinity_labels(self, conn):
        affinity_labels = set()
        affinity_labels_service = \
            conn.system_service().affinity_labels_service()
        affinity_labels_list = affinity_labels_service.list()
        for affinity_label in affinity_labels_list:
            affinity_labels.add(affinity_label.name)
        return list(affinity_labels)

    def _get_aaa_domains(self, conn):
        domains = []
        domains_service = conn.system_service().domains_service()
        domains_list = domains_service.list()
        for domain in domains_list:
            domains.append(domain.name)
        return domains

    def _get_vnic_profile_mapping(self, conn):
        networks = []
        vnic_profiles_service = conn.system_service().vnic_profiles_service()
        vnic_profile_list = vnic_profiles_service.list()
        for vnic_profile_item in vnic_profile_list:
            mapped_network = {}
            networks_list = conn.system_service().networks_service().list()
            network_name = ''
            for network_item in networks_list:
                if network_item.id == vnic_profile_item.network.id:
                    network_name = network_item.name
                    dc_name = conn.system_service().data_centers_service(). \
                        data_center_service(network_item.data_center.id). \
                        get()._name
                    break
            mapped_network['network_name'] = network_name
            mapped_network['network_dc'] = dc_name
            mapped_network['profile_name'] = vnic_profile_item.name
            # mapped_network['profile_id'] = vnic_profile_item.id
            networks.append(mapped_network)
        return networks

    def _key_setup(self, setup, key):
        if setup == 'primary':
            if key == 'dr_import_storages':
                return 'dr_primary_name'
            return 'primary_name'
        elif setup == 'secondary':
            if key == 'dr_import_storages':
                return 'dr_secondary_name'
            return 'secondary_name'

    def _validate_entity_exists(self, _list, var_file, key, setup):
        isValid = True
        key_setup = self._key_setup(setup, key)
        _mapping = var_file.get(key)
        if _mapping is None:
            return isValid
        for x in _mapping:
            if key_setup not in x.keys():
                print(
                    "%s%sdictionary key '%s' is not include in %s[%s].%s" %
                    (FAIL,
                     PREFIX,
                     key_setup,
                     key,
                     x.keys(),
                     END))
                isValid = False
            if isValid and x[key_setup] not in _list:
                print(
                    "%s%s%s entity '%s':'%s' does not exist in the "
                    "setup.\n%sThe entities which exists in the setup "
                    "are: %s.%s" %
                    (FAIL,
                     PREFIX,
                     key,
                     key_setup,
                     x[key_setup],
                     PREFIX,
                     _list,
                     END))
                isValid = False
        if isValid:
            print(
                "%s%sFinished validation for '%s' for key name "
                "'%s' with success.%s" %
                (INFO,
                 PREFIX,
                 key,
                 key_setup,
                 END))
        return isValid

    def _validate_hosted_engine(self, var_file):
        domains = var_file[self.domain_map]
        hosted = 'hosted_storage'
        primary = domain['dr_primary_name']
        secondary = domain['dr_secondary_name']
        for domain in domains:
            if (primary == hosted or secondary == hosted):
                print("%s%sHosted storage domains are not supported.%s"
                      % (FAIL,
                         PREFIX,
                         END))
                return False
        return True

    def _validate_duplicate_keys(self, var_file):
        isValid = True
        clusters = 'clusters'
        domains = 'domains'
        roles = 'roles'
        aff_group = 'aff_groups'
        aff_label = 'aff_labels'
        network = 'network'
        key1 = 'primary_name'
        key2 = 'secondary_name'

        duplicates = self._get_dups(
            var_file, [
                [clusters, self.cluster_map, key1, key2],
                [domains, self.domain_map, 'dr_primary_name',
                 'dr_secondary_name'],
                [roles, self.role_map, key1, key2],
                [aff_group, self.aff_group_map, key1, key2],
                [aff_label, self.aff_label_map, key1, key2]])
        duplicates[network] = self._get_dup_network(var_file)
        isValid = (not self._print_duplicate_keys(
            duplicates, [clusters, domains, roles, aff_group,
                         aff_label, network])) and isValid
        return isValid

    def _is_compatible_versions(self, var_file, _mapping):
        """ Validate cluster versions """
        # TODO: Add support for compatible cluster versions

    def _get_dups(self, var_file, mappings):
        duplicates = {}
        for mapping in mappings:
            _return_set = set()
            _mapping = var_file.get(mapping[1])
            if _mapping is None or len(_mapping) < 1:
                print("%s%smapping %s is empty in var file%s"
                      % (FAIL,
                         PREFIX,
                         mapping[1],
                         END))
                duplicates[mapping[0]] = _return_set
                continue
            _primary = set()
            _second = set()
            _return_set.update(
                set(x[mapping[2]]
                    for x in _mapping
                    if x[mapping[2]]
                    in _primary or _primary.add(x[mapping[2]])))
            _return_set.update(
                set(x[mapping[3]]
                    for x in _mapping
                    if x[mapping[3]]
                    in _second or _second.add(x[mapping[3]])))
            duplicates[mapping[0]] = _return_set
        return duplicates

    def _get_dup_network(self, var_file):
        _return_set = set()
        # TODO: Add data center also
        map_name = 'dr_network_mappings'
        _mapping = var_file.get(map_name)
        if _mapping is None or len(_mapping) < 1:
            print("%s%sNetwork has not been initialized in var file%s"
                  % (WARN,
                     PREFIX,
                     END))
            return _return_set

        # Check for profile + network name duplicates in primary
        _primary1 = set()
        key1_a = 'primary_profile_name'
        key1_b = 'primary_network_name'
        for x in _mapping:
            if (x[key1_a] is None or x[key1_b] is None):
                print("%s%sNetwork '%s' is not initialized in map %s %s%s"
                      % (FAIL,
                         PREFIX,
                         x,
                         x[key1_a],
                         x[key1_b],
                         END))
                exit()
            map_key = x[key1_a] + "_" + x[key1_b]
            if map_key in _primary1:
                _return_set.add(map_key)
            else:
                _primary1.add(map_key)

        # Check for profile + network name duplicates in secondary
        _second1 = set()
        val1_a = 'secondary_profile_name'
        val1_b = 'secondary_network_name'
        for x in _mapping:
            if (x[val1_a] is None or x[val1_b] is None):
                print("%s%sThe following network mapping is not "
                      "initialized in var file mapping:\n"
                      "  %s:'%s'\n  %s:'%s'%s"
                      % (FAIL,
                         PREFIX,
                         val1_a,
                         x[val1_a],
                         val1_b,
                         x[val1_b],
                         END))
                exit()
            map_key = x[val1_a] + "_" + x[val1_b]
            if map_key in _second1:
                _return_set.add(map_key)
            else:
                _second1.add(map_key)

        # TODO:  Once vnic profile will be validated, delete:
        #        Check for duplicates in primary_profile_id
        #        _primary2 = set()
        #        key = 'primary_profile_id'
        #        _return_set.update(set(x[key]
        #                               for x in
        #                               _mapping if x[key]
        #                               in _primary2 or _primary2.add(x[key])))
        #
        #        # Check for duplicates in secondary_profile_id
        #        _second2 = set()
        #        val = 'secondary_profile_id'
        #        _return_set.update(set(x[val]
        #                               for x in
        #                               _mapping if x[val]
        #                               in _second2 or _second2.add(x[val])))
        return _return_set


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


class ConnectSDK:
    primary_url, primary_user, primary_ca, primary_password = '', '', '', ''
    second_url, second_user, second_ca, second_password = '', '', '', ''
    prefix = ''
    error_msg = "%s%s The '%s' field in the %s setup is not " \
                "initialized in var file mapping.%s"

    def __init__(self, var_file, pass_file, vault_password):
        """
        ---
        dr_sites_primary_url: http://xxx.xx.xx.xxx:8080/ovirt-engine/api
        dr_sites_primary_username: admin@internal
        dr_sites_primary_ca_file: /etc/pki/ovirt-engine/ca.pem

        # Please fill in the following properties for the secondary site:
        dr_sites_secondary_url: http://yyy.yy.yy.yyy:8080/ovirt-engine/api
        dr_sites_secondary_username: admin@internal
        dr_sites_secondary_ca_file: /etc/pki/ovirt-engine_secondary/ca.pem
        """
        self.primary_url = var_file.get('dr_sites_primary_url')
        self.primary_user = var_file.get('dr_sites_primary_username')
        self.primary_ca = var_file.get('dr_sites_primary_ca_file')
        self.second_url = var_file.get('dr_sites_secondary_url')
        self.second_user = var_file.get('dr_sites_secondary_username')
        self.second_ca = var_file.get('dr_sites_secondary_ca_file')

        if (vault_password != ''):
            vault = Vault(vault_password)
            try:
                passwords = vault.load(open(pass_file).read())
                self.primary_password = passwords['dr_sites_primary_password']
                self.second_password = passwords['dr_sites_secondary_password']
            except BaseException:
                try:
                    print("%s%sCan not read passwords from vault."
                          " Will try to read as plain file.%s"
                          % (WARN,
                             PREFIX,
                             END))
                    self._plain_read(pass_file)
                except BaseException:
                    print("%s%sCan not read passwords from file%s"
                          % (FAIL,
                             PREFIX,
                             END))
        else:
            try:
                self._plain_read(pass_file)
            except BaseException:
                print("%s%sCan not read passwords from file%s"
                      % (FAIL,
                         PREFIX,
                         END))

    def _plain_read(self, pass_file):
        with open(pass_file) as file:
            passwords = file.read()
            info_dict = yaml.load(passwords)
            self.primary_password = \
                info_dict['dr_sites_primary_password']
            self.second_password = \
                info_dict['dr_sites_secondary_password']

    def validate_primary(self):
        isValid = True
        if self.primary_url is None:
            print(self.error_msg % (
                  FAIL,
                  PREFIX,
                  "url",
                  "primary",
                  END))
            isValid = False
        if self.primary_user is None:
            print(self.error_msg % (
                  FAIL,
                  PREFIX,
                  "username",
                  "primary",
                  END))
            isValid = False
        if self.primary_password is None:
            print(self.error_msg % (
                  FAIL,
                  PREFIX,
                  "password",
                  "primary",
                  END))
            isValid = False
        if self.primary_ca is None:
            print(self.error_msg % (
                  FAIL,
                  PREFIX,
                  "ca",
                  "primary",
                  END))
            isValid = False
        return isValid

    def validate_secondary(self):
        isValid = True
        if self.second_url is None:
            print(self.error_msg % (
                  FAIL,
                  PREFIX,
                  "url",
                  "secondary",
                  END))
            isValid = False
        if self.second_user is None:
            print(self.error_msg % (
                  FAIL,
                  PREFIX,
                  "username",
                  "secondary",
                  END))
            isValid = False
        if self.second_password is None:
            print(self.error_msg % (
                  FAIL,
                  PREFIX,
                  "password",
                  "secondary",
                  END))
            isValid = False
        if self.second_ca is None:
            print(self.error_msg % (
                  FAIL,
                  PREFIX,
                  "ca",
                  "secondary",
                  END))
            isValid = False
        return isValid

    def _validate_connection(self,
                             url,
                             username,
                             password,
                             ca):
        conn = None
        try:
            conn = self._connect_sdk(url,
                                     username,
                                     password,
                                     ca)
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
            return None
        return conn

    def connect_primary(self):
        return self._validate_connection(self.primary_url,
                                         self.primary_user,
                                         self.primary_password,
                                         self.primary_ca)

    def connect_secondary(self):
        return self._validate_connection(self.second_url,
                                         self.second_user,
                                         self.second_password,
                                         self.second_ca)

    def _connect_sdk(self, url, username, password, ca):
        connection = sdk.Connection(
            url=url,
            username=username,
            password=password,
            ca_file=ca,
        )
        return connection


if __name__ == "__main__":
    ValidateMappingFile().run('dr.conf', '/var/log/ovirt-dr/ovirt-dr.log')
