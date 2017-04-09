#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import (absolute_import, division, print_function)

"""
Ansible module to manage symbolic link alternatives.
(c) 2014, Gabe Mulley <gabe.mulley@gmail.com>
(c) 2015, David Wittman <dwittman@gmail.com>

This file is part of Ansible

Ansible is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Ansible is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
"""

ANSIBLE_METADATA = {'metadata_version': '1.0',
                    'status': ['preview'],
                    'supported_by': 'community'}


DOCUMENTATION = '''
---
module: alternatives
short_description: Manages alternative programs for common commands
description:
    - Manages symbolic links using the 'update-alternatives' tool
    - Useful when multiple programs are installed but provide similar functionality (e.g. different editors).
version_added: "1.6"
author:
    - "David Wittman (@DavidWittman)"
    - "Gabe Mulley (@mulby)"
options:
  name:
    description:
      - The generic name of the link.
    required: true
  path:
    description:
      - The path to the real executable that the link should point to.
    required: true
  link:
    description:
      - The path to the symbolic link that should point to the real executable.
      - This option is required on RHEL-based distributions
    required: false
  priority:
    description:
      - The priority of the alternative
    required: false
    default: 50
    version_added: "2.2"
  state:
    description:
      - The state of the link.
    required: false
    default: present
    choices: [ present, absent ]
    version_added: "2.4"
requirements: [ update-alternatives ]
'''

EXAMPLES = '''
- name: correct java version selected
  alternatives:
    name: java
    path: /usr/lib/jvm/java-7-openjdk-amd64/jre/bin/java

- name: alternatives link created
  alternatives:
    name: hadoop-conf
    link: /etc/hadoop/conf
    path: /etc/hadoop/conf.ansible

- name: make java 32 bit an alternative with low priority
  alternatives:
    name: java
    path: /usr/lib/jvm/java-7-openjdk-i386/jre/bin/java
    priority: -10

- name: remove a java version from the alternatives
  alternatives:
    name: java
    path: /usr/lib/jvm/java-7-openjdk-amd64/jre/bin/java
    state: absent
'''

import re
from ansible.module_utils.basic import AnsibleModule, subprocess
from ansible.module_utils.pycompat24 import get_exception

def get_current(module, cmd, name, link):
    """Get the options and the currently set value for the named alternative.

    If `link` is not specified, this value will be retrieved from the
    alternatives database.

    Returns a tuple of currently set value, possible options, and link path."""
    current_path = None
    all_alternatives = []

    # Run `update-alternatives --display <name>` to find existing alternatives
    (rc, display_output, _) = module.run_command(
        ['env', 'LC_ALL=C', cmd, '--display', name]
    )

    if rc == 0:
        # Alternatives already exist for this link group
        # Parse the output to determine the current path of the symlink and
        # available alternatives
        current_path_regex = re.compile(r'^\s*link currently points to (.*)$',
                                        re.MULTILINE)
        alternative_regex = re.compile(r'^(\/.*)\s-\spriority', re.MULTILINE)

        current_path = current_path_regex.search(display_output).group(1)
        all_alternatives = alternative_regex.findall(display_output)

        if not link:
            # Read the current symlink target from `update-alternatives --query`
            # in case we need to install the new alternative before setting it.
            #
            # This is only compatible on Debian-based systems, as the other
            # alternatives don't have --query available
            rc, query_output, _ = module.run_command(
                ['env', 'LC_ALL=C', cmd, '--query', name]
            )
            if rc == 0:
                for line in query_output.splitlines():
                    if line.startswith('Link:'):
                        link = line.split()[1]
                        break

    return current_path, all_alternatives, link

def set_alternative(module, cmd, name, path, link, priority,
        current_path, all_alternatives):
    """Set the current named alternative to the specified path.

    If not present in the currently configured alternatives, the requested
    alternative will be added with the specified priority.  The `link`
    parameter must be provided in this instance."""
    if current_path != path:
        if module.check_mode:
            module.exit_json(changed=True, current_path=current_path)
        try:
            # install the requested path if necessary
            if path not in all_alternatives:
                if not link:
                    module.fail_json(msg="Needed to install the alternative, "
                        "but unable to do so as we are missing the link")

                module.run_command(
                    [cmd, '--install', link, name, path, str(priority)],
                    check_rc=True
                )

            # select the requested path
            module.run_command(
                [cmd, '--set', name, path],
                check_rc=True
            )

            module.exit_json(changed=True)
        except subprocess.CalledProcessError:
            cpe = get_exception()
            module.fail_json(msg=str(dir(cpe)))
    else:
        module.exit_json(changed=False)

def remove_alternative(module, cmd, name, path, all_alternatives):
    """Remove the requested path if necessary"""
    if path in all_alternatives:
        try:
            module.run_command([cmd, '--remove', name, path], check_rc=True)
            module.exit_json(changed=True)
        except subprocess.CalledProcessError:
            cpe = get_exception()
            module.fail_json(msg=str(dir(cpe)))
    else:
        module.exit_json(changed=False)

def main():
    """Main module entrypoint"""
    module = AnsibleModule(
        argument_spec = dict(
            name = dict(required=True),
            path = dict(required=True, type='path'),
            link = dict(required=False, type='path'),
            priority = dict(required=False, type='int',
                            default=50),
            state = dict(choices=['present', 'absent'], default='present'),
        ),
        supports_check_mode=True,
    )

    params = module.params
    name = params['name']
    path = params['path']
    link = params['link']
    priority = params['priority']
    state = params['state']

    UPDATE_ALTERNATIVES = module.get_bin_path('update-alternatives', True)
    (current_path, all_alternatives, link) = get_current(
        module, UPDATE_ALTERNATIVES, name, link)

    if state == 'present':
        set_alternative(module, UPDATE_ALTERNATIVES, name, path, link, priority,
                        current_path, all_alternatives)
    elif state == 'absent':
        remove_alternative(module, UPDATE_ALTERNATIVES, name, path, all_alternatives)

if __name__ == '__main__':
    main()
