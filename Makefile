# ====================================================================
# Copyright 2017 Red Hat, Inc. and/or its affiliates.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# ====================================================================

#
# CUSTOMIZATION-BEGIN
#
BUILD_VALIDATION=1

PACKAGE_NAME=ovirt-ansible-disaster-recovery
RPM_TOPDIR?=$(PWD)/build/rpm
ANSIBLE_DISASTER_RECOVERY_ROLE_NAME=oVirt.disaster-recovery
PREFIX=/usr/local
SYSCONF_DIR=$(PREFIX)/etc
DATAROOT_DIR=$(PREFIX)/share
LOCALSTATE_DIR=$(PREFIX)/var
PKG_LOG_DIR=/var/log/$(PACKAGE_NAME)
PKG_DATA_DIR=$(DATAROOT_DIR)/$(PACKAGE_NAME)
PKG_ANSIBLE_ROLES_DATA_DIR=$(DATAROOT_DIR)/ansible/roles/$(ANSIBLE_DISASTER_RECOVERY_ROLE_NAME)
PKG_DATA_BIN_DIR=$(PKG_DATA_DIR)/bin
ENGINE_DATA_DIR=$(DATAROOT_DIR)/ovirt-engine
ENGINE_DATA_BIN_DIR=$(ENGINE_DATA_DIR)/bin
ENGINE_DATA_SETUP_DIR=$(ENGINE_DATA_DIR)/setup
PKG_SYSCONF_DIR=$(SYSCONF_DIR)/$(PACKAGE_NAME)
LOCALSTATE_DIR=$(PREFIX)/var
COLLECTD_STATE_DIR=$(LOCALSTATE_DIR)/lib/ovirt-collectd
COLLECTD_PGPASS=$(COLLECTD_STATE_DIR)/pgpass/engine.pgpass

#
# CUSTOMIZATION-END
#

include version.mak
RPM_VERSION=$(VERSION)
PACKAGE_VERSION=$(VERSION)$(if $(MILESTONE),_$(MILESTONE))
DISPLAY_VERSION=$(PACKAGE_VERSION)

TARBALL=$(PACKAGE_NAME)-$(PACKAGE_VERSION).tar.gz

.SUFFIXES:
.SUFFIXES: .in

.in:
	sed \
	-e "s|@DATAROOT_DIR@|$(DATAROOT_DIR)|g" \
	-e "s|@PKG_SYSCONF_DIR@|$(PKG_SYSCONF_DIR)|g" \
	-e "s|@PKG_DATA_DIR@|$(PKG_DATA_DIR)|g" \
	-e "s|@PKG_ANSIBLE_ROLES_DATA_DIR@|$(PKG_ANSIBLE_ROLES_DATA_DIR)|g" \
	-e "s|@PKG_DATA_BIN_DIR@|$(PKG_DATA_BIN_DIR)|g" \
	-e "s|@ENGINE_DATA_DIR@|$(ENGINE_DATA_DIR)|g" \
        -e "s|@ENGINE_LOG@|$(PKG_LOG_DIR)|g" \
	-e "s|@ENGINE_DATA_BIN_DIR@|$(ENGINE_DATA_BIN_DIR)|g" \
	-e "s|@ENGINE_DATA_SETUP_DIR@|$(ENGINE_DATA_SETUP_DIR)|g" \
        -e "s|@SETUP_LOG@|$(PKG_LOG_DIR)|g" \
	-e "s|@COLLECTD_PGPASS@|$(COLLECTD_PGPASS)|g" \
	-e "s|@RPM_VERSION@|$(RPM_VERSION)|g" \
	-e "s|@RPM_RELEASE@|$(RPM_RELEASE)|g" \
	-e "s|@PACKAGE_NAME@|$(PACKAGE_NAME)|g" \
	-e "s|@PACKAGE_VERSION@|$(PACKAGE_VERSION)|g" \
	-e "s|@DISPLAY_VERSION@|$(DISPLAY_VERSION)|g" \
	-e "s|@VERSION_MAJOR@|$(VERSION_MAJOR)|g" \
	-e "s|@VERSION_MINOR@|$(VERSION_MINOR)|g" \
	-e "s|@VERSION_PATCH_LEVEL@|$(VERSION_PATCH_LEVEL)|g" \
	$< > $@

GENERATED = \
	ovirt-ansible-disaster-recovery.spec \
	bin/config.sh \
	$(NULL)

all:	\
	generated-files \
	validations \
	$(NULL)

generated-files:	$(GENERATED)

clean:
	rm -rf $(GENERATED)

install: \
	all \
	install-packaging-files \
	install-artifacts \
	$(NULL)

.PHONY: ovirt-ansible-disaster-recovery.spec.in

dist:	ovirt-ansible-disaster-recovery.spec
	git ls-files | tar --files-from /proc/self/fd/0 -czf "$(TARBALL)" ovirt-ansible-disaster-recovery.spec
	@echo
	@echo For distro specific packaging refer to http://www.ovirt.org/Build_Binary_Package
	@echo

# copy SOURCEDIR to TARGETDIR
# exclude EXCLUDEGEN a list of files to exclude with .in
# exclude EXCLUDE a list of files.
copy-recursive:
	( cd "$(SOURCEDIR)" && find . -type d -printf '%P\n' ) | while read d; do \
		install -d -m 755 "$(TARGETDIR)/$${d}"; \
	done
	( \
		cd "$(SOURCEDIR)" && find . -type f -printf '%P\n' | \
		while read f; do \
			exclude=false; \
			for x in $(EXCLUDE_GEN); do \
				if [ "$(SOURCEDIR)/$${f}" = "$${x}.in" ]; then \
					exclude=true; \
					break; \
				fi; \
			done; \
			for x in $(EXCLUDE); do \
				if [ "$(SOURCEDIR)/$${f}" = "$${x}" ]; then \
					exclude=true; \
					break; \
				fi; \
			done; \
			$${exclude} || echo "$${f}"; \
		done \
	) | while read f; do \
		src="$(SOURCEDIR)/$${f}"; \
		dst="$(TARGETDIR)/$${f}"; \
		[ -x "$${src}" ] && MASK=0755 || MASK=0644; \
		[ -n "$(DEV_FLIST)" ] && echo "$${dst}" | sed 's#^$(PREFIX)/##' >> "$(DEV_FLIST)"; \
		install -T -m "$${MASK}" "$${src}" "$${dst}"; \
	done

validations:	generated-files
	if [ "$(BUILD_VALIDATION)" != 0 ]; then \
		build/shell-check.sh; \
	fi

install-artifacts:
	echo "ansible.cfg" "$(DESTDIR)$(PKG_DATA_DIR)"
	echo "$(PACKAGE_NAME).log" "$(PKG_LOG_DIR)"
	install -m 0644 "$(PACKAGE_NAME).log" "$(PKG_LOG_DIR)"
	install -m 0644 "ansible.cfg" "$(DESTDIR)$(PKG_DATA_DIR)"
	install -m 0644 "README.md" "$(DESTDIR)$(PKG_DATA_DIR)"
	# Create a link in the old location, for compatibility.
	# TODO make sure all users know about the new location and remove
	install -d "$(DESTDIR)$(PKG_DATA_DIR)/setup/ansible"

install-packaging-files: \
		$(GENERATED) \
		$(NULL)
	$(MAKE) copy-recursive SOURCEDIR=etc TARGETDIR="$(DESTDIR)$(PKG_SYSCONF_DIR)" EXCLUDE_GEN="$(GENERATED)"
	for d in bin inventory playbooks tools; do \
		$(MAKE) copy-recursive SOURCEDIR="$${d}" TARGETDIR="$(DESTDIR)$(PKG_DATA_DIR)/$${d}" EXCLUDE_GEN="$(GENERATED)"; \
	done
	for d in roles vars tasks; do \
		$(MAKE) copy-recursive SOURCEDIR="$${d}" TARGETDIR="$(DESTDIR)$(PKG_ANSIBLE_ROLES_DATA_DIR)/$${d}" EXCLUDE_GEN="$(GENERATED)"; \
	done

