########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#    * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    * See the License for the specific language governing permissions and
#    * limitations under the License.


from setuptools import setup

# Replace the place holders with values for your project

setup(

    # Do not use underscores in the plugin name.
    name='cloudify-flexiant-plugin',

    version='3.3a5',
    author='alen',
    author_email='alen.buhanec@xlab.si',
    description='Flexiant FCO plugin for Cloudify 3.x',

    # This must correspond to the actual packages in the plugin.
    packages=['fcoclient', 'resttypes', 'typed', 'cfy'],

    license='LICENSE',
    zip_safe=False,
    install_requires=[
        # 'cloudify-plugins-common>=3.3a5',
        'cloudify-plugins-common>=3.3a4',
        'enum34',
        'requests',
        'pycrypto',
        'paramiko',
        'spur',
        'fabric',
        'scp'
    ],
    test_requires=[
        # 'cloudify-dsl-parser>=3.3a5',
        'cloudify-dsl-parser>=3.3a4',
        'nose'
    ],
    dependency_links=[
        'http://github.com/cloudify-cosmo/cloudify-rest-client/tarball/3.3m5#egg=cloudify-rest-client-3.3a5',  # noqa
        'http://github.com/cloudify-cosmo/cloudify-plugins-common/archive/3.3m5.zip#egg=cloudify-plugins-common-3.3a5',  # noqa
        'http://github.com/cloudify-cosmo/cloudify-dsl-parser/tarball/3.3m5#egg=cloudify-dsl-parser-3.3a5'  # noqa
    ]
)
