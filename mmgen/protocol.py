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

"""
protocol.py: Coin protocol functions, classes and methods
"""

import sys,os,hashlib
from collections import namedtuple,OrderedDict

from mmgen.util import msg,ymsg,Msg,ydie
from mmgen.devtools import *
from mmgen.obj import BTCAmt,LTCAmt,BCHAmt,B2XAmt,ETHAmt
from mmgen.globalvars import g
import mmgen.bech32 as bech32

parsed_wif = namedtuple('parsed_wif',['sec','pubkey_type','compressed'])
parsed_addr = namedtuple('parsed_addr',['bytes','fmt'])

def hash160(hexnum): # take hex, return hex - OP_HASH160
	return hashlib.new('ripemd160',hashlib.sha256(bytes.fromhex(hexnum)).digest()).hexdigest()

def hash256(hexnum): # take hex, return hex - OP_HASH256
	return hashlib.sha256(hashlib.sha256(bytes.fromhex(hexnum)).digest()).hexdigest()

def hash256bytes(bstr): # bytes in, bytes out - OP_HASH256
	return hashlib.sha256(hashlib.sha256(bstr).digest()).digest()

_b58a='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'

# From en.bitcoin.it:
#  The Base58 encoding used is home made, and has some differences.
#  Especially, leading zeroes are kept as single zeroes when conversion happens.
# Test: 5JbQQTs3cnoYN9vDYaGY6nhQ1DggVsY4FJNBUfEfpSQqrEp3srk
# The 'zero address':
# 1111111111111111111114oLvT2 (pubkeyhash = '\0'*20)

def _b58chk_encode(bstr):
	lzeroes = len(bstr) - len(bstr.lstrip(b'\x00'))
	def do_enc(n):
		while n:
			yield _b58a[n % 58]
			n //= 58
	return ('1' * lzeroes) + ''.join(do_enc(int.from_bytes(bstr+hash256bytes(bstr)[:4],'big')))[::-1]

def _b58chk_decode(s):
	lzeroes = len(s) - len(s.lstrip('1'))
	res = sum(_b58a.index(ch) * 58**n for n,ch in enumerate(s[::-1]))
	bl = res.bit_length()
	out = b'\x00' * lzeroes + res.to_bytes(bl//8 + bool(bl%8),'big')
	if out[-4:] != hash256bytes(out[:-4])[:4]:
		raise ValueError('_b58chk_decode(): incorrect checksum')
	return out[:-4]

# chainparams.cpp
class BitcoinProtocol(MMGenObject):
	name            = 'bitcoin'
	daemon_name     = 'bitcoind'
	daemon_family   = 'bitcoind'
	addr_ver_bytes  = { '00': 'p2pkh', '05': 'p2sh' }
	addr_len        = 20
	wif_ver_num     = { 'std': '80' }
	mmtypes         = ('L','C','S','B')
	dfl_mmtype      = 'L'
	data_subdir     = ''
	rpc_port        = 8332
	secs_per_block  = 600
	coin_amt        = BTCAmt
	max_tx_fee      = BTCAmt('0.003')
	daemon_data_dir = os.path.join(os.getenv('APPDATA'),'Bitcoin') if g.platform == 'win' \
						else os.path.join(g.home_dir,'.bitcoin')
	daemon_data_subdir = ''
	sighash_type = 'ALL'
	block0 = '000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f'
	forks = [ # height, hash, name, replayable
		(478559,'00000000000000000019f112ec0a9982926f1258cdcc558dd7c3b7e5dc7fa148','bch',False),
		(None,'','b2x',True)
	]
	caps               = ('rbf','segwit')
	mmcaps             = ('key','addr','rpc','tx')
	base_coin          = 'BTC'
	base_proto         = 'Bitcoin'
	# From BIP173: witness version 'n' is stored as 'OP_n'. OP_0 is encoded as 0x00,
	# but OP_1 through OP_16 are encoded as 0x51 though 0x60 (81 to 96 in decimal).
	witness_vernum_hex = '00'
	witness_vernum     = int(witness_vernum_hex,16)
	bech32_hrp         = 'bc'
	sign_mode          = 'daemon'
	secp256k1_ge       = 0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141
	privkey_len        = 32
	avg_bdi            = int(9.7 * 60) # average block discovery interval (historical)

	@classmethod
	def addr_fmt_to_ver_bytes(cls,req_fmt,return_hex=False):
		for ver_hex,fmt in cls.addr_ver_bytes.items():
			if req_fmt == fmt:
				return ver_hex if return_hex else bytes.fromhex(ver_hex)
		return False

	@classmethod
	def is_testnet(cls):
		return cls.__name__[-15:] == 'TestnetProtocol'

	@staticmethod
	def get_protocol_by_chain(chain):
		return CoinProtocol(g.coin,{'mainnet':False,'testnet':True,'regtest':True}[chain])

	@classmethod
	def cap(cls,s): return s in cls.caps

	@classmethod
	def preprocess_key(cls,sec,pubkey_type):
		# Key must be non-zero and less than group order of secp256k1 curve
		if 0 < int.from_bytes(sec,'big') < cls.secp256k1_ge:
			return sec
		else: # chance of this is less than 1 in 2^127
			pk = int.from_bytes(sec,'big')
			if pk == 0: # chance of this is 1 in 2^256
				ydie(3,'Private key is zero!')
			elif pk == cls.secp256k1_ge: # ditto
				ydie(3,'Private key == secp256k1_ge!')
			else:
				if not g.test_suite:
					ymsg('Warning: private key is greater than secp256k1 group order!:\n  {}'.format(hexpriv))
				return (pk % cls.secp256k1_ge).to_bytes(cls.privkey_len,'big')

	@classmethod
	def hex2wif(cls,hexpriv,pubkey_type,compressed): # input is preprocessed hex
		sec = bytes.fromhex(hexpriv)
		assert len(sec) == cls.privkey_len, '{} bytes: incorrect private key length!'.format(len(sec))
		assert pubkey_type in cls.wif_ver_num, '{!r}: invalid pubkey_type'.format(pubkey_type)
		return _b58chk_encode(
			bytes.fromhex(cls.wif_ver_num[pubkey_type])
			+ sec
			+ (b'',b'\x01')[bool(compressed)])

	@classmethod
	def parse_wif(cls,wif):
		key = _b58chk_decode(wif)

		for k,v in cls.wif_ver_num.items():
			v = bytes.fromhex(v)
			if key[:len(v)] == v:
				pubkey_type = k
				key = key[len(v):]
				break
		else:
			raise ValueError('invalid WIF version number')

		if len(key) == cls.privkey_len + 1:
			assert key[-1] == 0x01,'{!r}: invalid compressed key suffix byte'.format(key[-1])
			compressed = True
		elif len(key) == cls.privkey_len:
			compressed = False
		else:
			raise ValueError('{}: invalid key length'.format(len(key)))

		return parsed_wif(key[:cls.privkey_len], pubkey_type, compressed)

	@classmethod
	def get_addr_len(cls,addr_fmt):
		return cls.addr_len

	@classmethod
	def parse_addr_bytes(cls,addr_bytes):
		for ver_hex,addr_fmt in cls.addr_ver_bytes.items():
			ver_bytes = bytes.fromhex(ver_hex)
			vlen = len(ver_bytes)
			if addr_bytes[:vlen] == ver_bytes:
				if len(addr_bytes[vlen:]) == cls.get_addr_len(addr_fmt):
					return parsed_addr( addr_bytes[vlen:], addr_fmt )

		return False

	@classmethod
	def parse_addr(cls,addr):

		if 'B' in cls.mmtypes and addr[:len(cls.bech32_hrp)] == cls.bech32_hrp:
			ret = bech32.decode(cls.bech32_hrp,addr)

			if ret[0] != cls.witness_vernum:
				msg('{}: Invalid witness version number'.format(ret[0]))
				return False

			return parsed_addr( bytes(ret[1]), 'bech32' ) if ret[1] else False

		return cls.parse_addr_bytes(_b58chk_decode(addr))

	@classmethod
	def pubhash2addr(cls,pubkey_hash,p2sh):
		assert len(pubkey_hash) == 40,'{}: invalid length for pubkey hash'.format(len(pubkey_hash))
		s = cls.addr_fmt_to_ver_bytes(('p2pkh','p2sh')[p2sh],return_hex=True) + pubkey_hash
		return _b58chk_encode(bytes.fromhex(s))

	# Segwit:
	@classmethod
	def pubhex2redeem_script(cls,pubhex):
		# https://bitcoincore.org/en/segwit_wallet_dev/
		# The P2SH redeemScript is always 22 bytes. It starts with a OP_0, followed
		# by a canonical push of the keyhash (i.e. 0x0014{20-byte keyhash})
		return cls.witness_vernum_hex + '14' + hash160(pubhex)

	@classmethod
	def pubhex2segwitaddr(cls,pubhex):
		return cls.pubhash2addr(hash160(cls.pubhex2redeem_script(pubhex)),p2sh=True)

	@classmethod
	def pubhash2bech32addr(cls,pubhash):
		d = list(bytes.fromhex(pubhash))
		return bech32.bech32_encode(cls.bech32_hrp,[cls.witness_vernum]+bech32.convertbits(d,8,5))

class BitcoinTestnetProtocol(BitcoinProtocol):
	addr_ver_bytes       = { '6f': 'p2pkh', 'c4': 'p2sh' }
	wif_ver_num          = { 'std': 'ef' }
	data_subdir          = 'testnet'
	daemon_data_subdir   = 'testnet3'
	rpc_port             = 18332
	bech32_hrps          = {'testnet':'tb','regtest':'bcrt'}

class BitcoinCashProtocol(BitcoinProtocol):
	# TODO: assumes MSWin user installs in custom dir 'Bitcoin_ABC'
	daemon_name    = 'bitcoind-abc'
	daemon_data_dir = os.path.join(os.getenv('APPDATA'),'Bitcoin_ABC') if g.platform == 'win' \
						else os.path.join(g.home_dir,'.bitcoin-abc')
	rpc_port       = 8442
	mmtypes        = ('L','C')
	sighash_type   = 'ALL|FORKID'
	forks = [
		(478559,'000000000000000000651ef99cb9fcbe0dadde1d424bd9f15ff20136191a5eec','btc',False)
	]
	caps = ()
	coin_amt        = BCHAmt
	max_tx_fee      = BCHAmt('0.1')

	@classmethod
	def pubhex2redeem_script(cls,pubhex): raise NotImplementedError
	@classmethod
	def pubhex2segwitaddr(cls,pubhex):    raise NotImplementedError

class BitcoinCashTestnetProtocol(BitcoinCashProtocol):
	rpc_port      = 18442
	addr_ver_bytes = { '6f': 'p2pkh', 'c4': 'p2sh' }
	wif_ver_num   = { 'std': 'ef' }
	data_subdir   = 'testnet'
	daemon_data_subdir = 'testnet3'

class B2XProtocol(BitcoinProtocol):
	daemon_name     = 'bitcoind-2x'
	daemon_data_dir = os.path.join(os.getenv('APPDATA'),'Bitcoin_2X') if g.platform == 'win' \
						else os.path.join(g.home_dir,'.bitcoin-2x')
	rpc_port        = 8338
	coin_amt        = B2XAmt
	max_tx_fee      = B2XAmt('0.1')
	forks = [
		(None,'','btc',True) # activation: 494784
	]

class B2XTestnetProtocol(B2XProtocol):
	addr_ver_bytes     = { '6f': 'p2pkh', 'c4': 'p2sh' }
	wif_ver_num        = { 'std': 'ef' }
	data_subdir        = 'testnet'
	daemon_data_subdir = 'testnet5'
	rpc_port           = 18338

class LitecoinProtocol(BitcoinProtocol):
	block0         = '12a765e31ffd4059bada1e25190f6e98c99d9714d334efa41a195a7e7e04bfe2'
	name           = 'litecoin'
	daemon_name    = 'litecoind'
	daemon_data_dir = os.path.join(os.getenv('APPDATA'),'Litecoin') if g.platform == 'win' \
						else os.path.join(g.home_dir,'.litecoin')
	addr_ver_bytes = OrderedDict((('30','p2pkh'), ('32','p2sh'), ('05','p2sh'))) # new p2sh ver 0x32 must come first
	wif_ver_num    = { 'std': 'b0' }
	mmtypes         = ('L','C','S','B')
	secs_per_block = 150
	rpc_port       = 9332
	coin_amt       = LTCAmt
	max_tx_fee     = LTCAmt('0.3')
	base_coin      = 'LTC'
	forks          = []
	bech32_hrp     = 'ltc'
	avg_bdi        = 2 * 60

class LitecoinTestnetProtocol(LitecoinProtocol):
	# addr ver nums same as Bitcoin testnet, except for 'p2sh'
	addr_ver_bytes = OrderedDict((('6f','p2pkh'), ('3a','p2sh'), ('c4','p2sh')))
	wif_ver_num    = { 'std': 'ef' } # same as Bitcoin testnet
	data_subdir    = 'testnet'
	daemon_data_subdir = 'testnet4'
	rpc_port       = 19332
	bech32_hrps    = {'testnet':'tltc','regtest':'rltc'}

class BitcoinProtocolAddrgen(BitcoinProtocol): mmcaps = ('key','addr')
class BitcoinTestnetProtocolAddrgen(BitcoinTestnetProtocol): mmcaps = ('key','addr')

class DummyWIF(object):

	@classmethod
	def hex2wif(cls,hexpriv,pubkey_type,compressed):
		n = cls.name.capitalize()
		assert pubkey_type == cls.pubkey_type,'{}: invalid pubkey_type for {}!'.format(pubkey_type,n)
		assert compressed == False,'{} does not support compressed pubkeys!'.format(n)
		return hexpriv

	@classmethod
	def parse_wif(cls,wif):
		return parsed_wif(bytes.fromhex(wif), cls.pubkey_type, False)

class EthereumProtocol(DummyWIF,BitcoinProtocol):

	addr_len   = 20
	mmtypes    = ('E',)
	dfl_mmtype = 'E'
	name = 'ethereum'
	base_coin = 'ETH'
	pubkey_type = 'std' # required by DummyWIF

	data_subdir = ''
	daemon_name = 'parity'
	daemon_family = 'parity'
	rpc_port    = 8545
	mmcaps      = ('key','addr','rpc')
	coin_amt    = ETHAmt
	max_tx_fee  = ETHAmt('0.005')
	chain_name  = 'foundation'
	sign_mode   = 'standalone'
	caps        = ('token',)
	base_proto  = 'Ethereum'

	@classmethod
	def parse_addr(cls,addr):
		from mmgen.util import is_hex_str_lc
		if is_hex_str_lc(addr) and len(addr) == cls.addr_len * 2:
			return parsed_addr( bytes.fromhex(addr), 'ethereum' )
		if g.debug: Msg("Invalid address '{}'".format(addr))
		return False

	@classmethod
	def pubhash2addr(cls,pubkey_hash,p2sh):
		assert len(pubkey_hash) == 40,'{}: invalid length for pubkey hash'.format(len(pubkey_hash))
		assert not p2sh,'Ethereum has no P2SH address format'
		return pubkey_hash

class EthereumTestnetProtocol(EthereumProtocol):
	data_subdir = 'testnet'
	rpc_port    = 8547 # start Parity with --jsonrpc-port=8547 or --ports-shift=2
	chain_name  = 'kovan'

class EthereumClassicProtocol(EthereumProtocol):
	name       = 'ethereumClassic'
	class_pfx  = 'Ethereum'
	rpc_port   = 8555 # start Parity with --jsonrpc-port=8555 or --ports-shift=10
	chain_name = 'ethereum_classic' # chain_id 0x3d (61)

class EthereumClassicTestnetProtocol(EthereumClassicProtocol):
	rpc_port   = 8557 # start Parity with --jsonrpc-port=8557 or --ports-shift=12
	chain_name = 'classic-testnet' # aka Morden, chain_id 0x3e (62) (UNTESTED)

class ZcashProtocol(BitcoinProtocolAddrgen):
	name         = 'zcash'
	base_coin    = 'ZEC'
	addr_ver_bytes = { '1cb8': 'p2pkh', '1cbd': 'p2sh', '169a': 'zcash_z', 'a8abd3': 'viewkey' }
	wif_ver_num  = { 'std': '80', 'zcash_z': 'ab36' }
	mmtypes      = ('L','C','Z')
	dfl_mmtype   = 'L'

	@classmethod
	def get_addr_len(cls,addr_fmt):
		return (20,64)[addr_fmt in ('zcash_z','viewkey')]

	@classmethod
	def preprocess_key(cls,sec,pubkey_type):
		if pubkey_type == 'zcash_z': # zero the first four bits
			return bytes([sec[0] & 0x0f]) + sec[1:]
		else:
			return super(cls,cls).preprocess_key(sec,pubkey_type)

	@classmethod
	def pubhash2addr(cls,pubkey_hash,p2sh):
		hl = len(pubkey_hash)
		if hl == 40:
			return super(cls,cls).pubhash2addr(pubkey_hash,p2sh)
		elif hl == 128:
			raise NotImplementedError('Zcash z-addresses have no pubkey hash')
		else:
			raise ValueError('{}: incorrect pubkey_hash length'.format(hl))

class ZcashTestnetProtocol(ZcashProtocol):
	wif_ver_num  = { 'std': 'ef', 'zcash_z': 'ac08' }
	addr_ver_bytes = { '1d25': 'p2pkh', '1cba': 'p2sh', '16b6': 'zcash_z', 'a8ac0c': 'viewkey' }

# https://github.com/monero-project/monero/blob/master/src/cryptonote_config.h
class MoneroProtocol(DummyWIF,BitcoinProtocolAddrgen):
	name         = 'monero'
	base_coin    = 'XMR'
	addr_ver_bytes = { '12': 'monero', '2a': 'monero_sub' }
	addr_len     = 68
	wif_ver_num  = {}
	mmtypes      = ('M',)
	dfl_mmtype   = 'M'
	pubkey_type = 'monero' # required by DummyWIF

	@classmethod
	def preprocess_key(cls,sec,pubkey_type): # reduce key
		from mmgen.ed25519 import l
		n = int.from_bytes(sec[::-1],'big') % l
		return int.to_bytes(n,cls.privkey_len,'big')[::-1]

	@classmethod
	def parse_addr(cls,addr):

		from mmgen.baseconv import baseconv,is_b58_str

		def b58dec(addr_str):
			l = len(addr_str)
			a = b''.join([baseconv.tobytes(addr_str[i*11:i*11+11],'b58',pad=8) for i in range(l//11)])
			b = baseconv.tobytes(addr_str[-(l%11):],'b58',pad=5)
			return a + b

		ret = b58dec(addr)

		try:
			assert not g.use_internal_keccak_module
			from sha3 import keccak_256
		except:
			from mmgen.keccak import keccak_256

		chk = keccak_256(ret[:-4]).digest()[:4]
		assert ret[-4:] == chk,'{}: incorrect checksum.  Correct value: {}'.format(ret[-4:].hex(),chk.hex())

		return cls.parse_addr_bytes(ret)

class MoneroTestnetProtocol(MoneroProtocol):
	addr_ver_bytes = { '35': 'monero', '3f': 'monero_sub' }

class CoinProtocol(MMGenObject):
	pi = namedtuple('proto_info',['main_cls','test_cls','trust_level']) # trust levels: see altcoin.py
	coins = {
		'btc': pi(BitcoinProtocol,BitcoinTestnetProtocol,5),
		'bch': pi(BitcoinCashProtocol,BitcoinCashTestnetProtocol,5),
		'ltc': pi(LitecoinProtocol,LitecoinTestnetProtocol,5),
		'eth': pi(EthereumProtocol,EthereumTestnetProtocol,4),
		'etc': pi(EthereumClassicProtocol,EthereumClassicTestnetProtocol,4),
		'zec': pi(ZcashProtocol,ZcashTestnetProtocol,2),
		'xmr': pi(MoneroProtocol,MoneroTestnetProtocol,4)
	}
	core_coins = tuple(coins.keys())

	def __new__(cls,coin,testnet):
		coin = coin.lower()
		assert type(testnet) == bool
		m = "{}: not a valid coin for network {}\nSupported coins: {}"
		assert coin in cls.coins, m.format(coin.upper(),g.network.upper(),' '.join(cls.list_coins()))
		proto = cls.coins[coin][testnet]
		if hasattr(proto,'bech32_hrps'):
			proto.bech32_hrp = proto.bech32_hrps[('testnet','regtest')[g.regtest]]
		return proto

	@classmethod
	def list_coins(cls):
		return [c.upper() for c in cls.coins]

	@classmethod
	def get_base_coin_from_name(cls,name):
		for (proto,foo) in cls.coins.values():
			if name == proto.__name__[:-8].lower():
				return proto.base_coin
		return False

def init_genonly_altcoins(usr_coin=None):
	"""
	Initialize altcoin protocol class or classes for current network.
	If usr_coin is a core coin, initialization is skipped.
	If usr_coin has a trust level of -1, an exception is raised.
	If usr_coin is None, initializes all coins for current network with trust level >-1.
	Returns trust_level of usr_coin, or 0 (untrusted) if usr_coin is None.
	"""
	from mmgen.altcoin import CoinInfo as ci
	data = { 'mainnet': (), 'testnet': () }
	networks = ['mainnet'] + (['testnet'] if g.testnet else [])

	if usr_coin == None:
		for network in networks:
			data[network] = ci.get_supported_coins(network)
		trust_level = 0
	else:
		if usr_coin.lower() in CoinProtocol.core_coins: # core coin, so return immediately
			return CoinProtocol.coins[usr_coin.lower()].trust_level
		for network in networks:
			data[network] = (ci.get_entry(usr_coin,network),)

		cinfo = data[g.network][0]
		if not cinfo:
			m = '{!r}: unrecognized coin for network {}'
			raise ValueError(m.format(usr_coin.upper(),g.network.upper()))
		if cinfo.trust_level == -1:
			m = '{!r}: unsupported (disabled) coin for network {}'
			raise ValueError(m.format(usr_coin.upper(),g.network.upper()))

		trust_level = cinfo.trust_level

	exec(make_init_genonly_altcoins_str(data),globals(),globals())
	return trust_level

def make_init_genonly_altcoins_str(data):

	def make_proto(e,testnet=False):
		tn_str = 'Testnet' if testnet else ''
		proto,coin = '{}{}Protocol'.format(e.name,tn_str),e.symbol
		if proto[0] in '0123456789': proto = 'X_'+proto
		if proto in globals(): return ''
		if coin.lower() in CoinProtocol.coins: return ''

		def num2hexstr(n):
			return "'{:0{}x}'".format(n,(4,2)[n < 256])

		o  = ['class {}(Bitcoin{}ProtocolAddrgen):'.format(proto,tn_str)]
		o += ["base_coin = '{}'".format(coin)]
		o += ["name = '{}'".format(e.name.lower())]
		o += ["nameCaps = '{}'".format(e.name)]
		o += ["addr_ver_bytes = {{ {}: 'p2pkh'{} }}".format(
			num2hexstr(e.p2pkh_info[0]),
			", {}: 'p2sh'".format(num2hexstr(e.p2sh_info[0])) if e.p2sh_info else ''
		)]
		o += ["wif_ver_num = {{ 'std': {} }}".format(num2hexstr(e.wif_ver_num))]
		o += ["mmtypes = ('L','C'{})".format(",'S'" if e.has_segwit else '')]
		o += ["dfl_mmtype = '{}'".format('L')]
		return '\n\t'.join(o) + '\n'

	out = ''
	for e in data['mainnet']:
		out += make_proto(e)
	for e in data['testnet']:
		out += make_proto(e,testnet=True)

	tn_coins = [e.symbol for e in data['testnet']]
	fs = "CoinProtocol.coins['{}'] = ({}Protocol,{})\n"
	for e in data['mainnet']:
		proto,coin = e.name,e.symbol
		if proto[0] in '0123456789': proto = 'X_'+proto
		if proto+'Protocol' in globals(): continue
		if coin.lower() in CoinProtocol.coins: continue
		out += fs.format(coin.lower(),proto,('None',proto+'TestnetProtocol')[coin in tn_coins])
	return out

def init_coin(coin,testnet=None):
	if testnet is not None:
		g.testnet = testnet
	g.network = ('mainnet','testnet')[g.testnet]
	coin = coin.upper()
	g.coin = coin
	g.proto = CoinProtocol(coin,g.testnet)
	return g.proto
