#!/usr/bin/env python3
#
# mmgen = Multi-Mode GENerator, command-line Bitcoin cold storage solution
# Copyright (C)2013-2020 The MMGen Project <mmgen@tuta.io>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import sys,os,subprocess
from shutil import copy2

sys_ver = sys.version_info[:2]
req_ver = (3,7)
ver2f = lambda t: float('{}.{:03}'.format(*t))

if ver2f(sys_ver) < ver2f(req_ver):
	m = '{}.{}: wrong Python version.  MMGen requires Python {}.{} or greater\n'
	sys.stderr.write(m.format(*sys_ver,*req_ver))
	sys.exit(1)

have_msys2 = subprocess.check_output(['uname','-s']).strip()[:7] == b'MSYS_NT'

from distutils.core import setup,Extension
from distutils.command.build_ext import build_ext
from distutils.command.install_data import install_data

cwd = os.getcwd()

def copy_owner(a,b):
	st = os.stat(a)
	try: os.chown(b,st.st_uid,st.st_gid,follow_symlinks=False)
	except: pass

# install extension module in repository after building
class my_build_ext(build_ext):
	def build_extension(self,ext):
		build_ext.build_extension(self,ext)
		ext_src = self.get_ext_fullpath(ext.name)
		ext_dest = os.path.join('mmgen',os.path.basename(ext_src))
		try: os.unlink(ext_dest)
		except: pass
		os.chmod(ext_src,0o755)
		print('copying {} to {}'.format(ext_src,ext_dest))
		copy2(ext_src,ext_dest)
		copy_owner(cwd,ext_dest)

def link_or_copy(tdir,a,b):
	os.chdir(tdir)
	try: os.unlink(b)
	except FileNotFoundError: pass
	copy2(a,b) if have_msys2 else os.symlink(a,b)
	copy_owner(a,b)
	os.chdir(cwd)

class my_install_data(install_data):
	def run(self):
		for f in 'mmgen.cfg','mnemonic.py','mn_wordlist.c':
			os.chmod(os.path.join('data_files',f),0o644)
		link_or_copy('test','start-coin-daemons.py','stop-coin-daemons.py')
		install_data.run(self)

module1 = Extension(
	name         = 'mmgen.secp256k1',
	sources      = ['extmod/secp256k1mod.c'],
	libraries    = ['secp256k1'] + ([],['gmp'])[have_msys2],
	library_dirs = ['/usr/local/lib',r'C:\msys64\mingw64\lib',r'C:\msys64\usr\lib'],
	include_dirs = ['/usr/local/include',r'C:\msys64\mingw64\include',r'C:\msys64\usr\include'],
	)

from mmgen.globalvars import g
setup(
		name         = 'mmgen',
		description  = 'A complete Bitcoin offline/online wallet solution for the command line',
		version      = g.version,
		author       = g.author,
		author_email = g.email,
		url          = g.proj_url,
		license      = 'GNU GPL v3',
		platforms    = 'Linux, MS Windows, Raspberry Pi/Raspbian, Orange Pi/Armbian',
		keywords     = g.keywords,
		cmdclass     = { 'build_ext': my_build_ext, 'install_data': my_install_data },
		ext_modules  = [module1],
		data_files = [('share/mmgen', [
				'data_files/mmgen.cfg',     # source files must have 0644 mode
				'data_files/mn_wordlist.c',
				'data_files/mnemonic.py'
				]),],
		py_modules = [
			'mmgen.__init__',
			'mmgen.addr',
			'mmgen.altcoin',
			'mmgen.baseconv',
			'mmgen.bech32',
			'mmgen.bip39',
			'mmgen.cfg',
			'mmgen.color',
			'mmgen.common',
			'mmgen.crypto',
			'mmgen.devtools',
			'mmgen.ed25519',
			'mmgen.ed25519ll_djbec',
			'mmgen.exception',
			'mmgen.filename',
			'mmgen.globalvars',
			'mmgen.keccak',
			'mmgen.license',
			'mmgen.mn_entry',
			'mmgen.mn_electrum',
			'mmgen.mn_monero',
			'mmgen.mn_tirosh',
			'mmgen.obj',
			'mmgen.opts',
			'mmgen.protocol',
			'mmgen.regtest',
			'mmgen.rpc',
			'mmgen.seed',
			'mmgen.sha2',
			'mmgen.term',
			'mmgen.daemon',
			'mmgen.tool',
			'mmgen.tw',
			'mmgen.tx',
			'mmgen.txsign',
			'mmgen.util',

			'mmgen.altcoins.__init__',

			'mmgen.altcoins.eth.__init__',
			'mmgen.altcoins.eth.contract',
			'mmgen.altcoins.eth.obj',
			'mmgen.altcoins.eth.tx',
			'mmgen.altcoins.eth.tw',

			'mmgen.altcoins.eth.pyethereum.__init__',
			'mmgen.altcoins.eth.pyethereum.transactions',
			'mmgen.altcoins.eth.pyethereum.utils',

			'mmgen/altcoins/eth/rlp/__init__',
			'mmgen/altcoins/eth/rlp/atomic',
			'mmgen/altcoins/eth/rlp/codec',
			'mmgen/altcoins/eth/rlp/exceptions',
			'mmgen/altcoins/eth/rlp/sedes/__init__',
			'mmgen/altcoins/eth/rlp/sedes/big_endian_int',
			'mmgen/altcoins/eth/rlp/sedes/binary',
			'mmgen/altcoins/eth/rlp/sedes/boolean',
			'mmgen/altcoins/eth/rlp/sedes/lists',
			'mmgen/altcoins/eth/rlp/sedes/raw',
			'mmgen/altcoins/eth/rlp/sedes/serializable',
			'mmgen/altcoins/eth/rlp/sedes/text',

			'mmgen.main',
			'mmgen.main_addrgen',
			'mmgen.main_addrimport',
			'mmgen.main_autosign',
			'mmgen.main_passgen',
			'mmgen.main_regtest',
			'mmgen.main_seedjoin',
			'mmgen.main_split',
			'mmgen.main_tool',
			'mmgen.main_txbump',
			'mmgen.main_txcreate',
			'mmgen.main_txdo',
			'mmgen.main_txsend',
			'mmgen.main_txsign',
			'mmgen.main_wallet',

			'mmgen.share.__init__',
			'mmgen.share.Opts',
		],
		scripts = [
			'cmds/mmgen-addrgen',
			'cmds/mmgen-keygen',
			'cmds/mmgen-passgen',
			'cmds/mmgen-addrimport',
			'cmds/mmgen-passchg',
			'cmds/mmgen-regtest',
			'cmds/mmgen-subwalletgen',
			'cmds/mmgen-walletchk',
			'cmds/mmgen-walletconv',
			'cmds/mmgen-walletgen',
			'cmds/mmgen-seedsplit',
			'cmds/mmgen-seedjoin',
			'cmds/mmgen-split',
			'cmds/mmgen-txcreate',
			'cmds/mmgen-txbump',
			'cmds/mmgen-txsign',
			'cmds/mmgen-txsend',
			'cmds/mmgen-txdo',
			'cmds/mmgen-tool',
			'cmds/mmgen-autosign'
		]
	)
