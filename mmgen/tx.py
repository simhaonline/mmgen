#!/usr/bin/env python
#
# mmgen = Multi-Mode GENerator, command-line Bitcoin cold storage solution
# Copyright (C) 2013-2014 by philemon <mmgen-py@yandex.com>
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
tx.py:  Bitcoin transaction routines
"""

from binascii import unhexlify
from mmgen.util import *
import sys, os
from decimal import Decimal
import mmgen.config as g

txmsg = {
'not_enough_btc': "Not enough BTC in the inputs for this transaction (%s BTC)",
'throwaway_change': """
ERROR: This transaction produces change (%s BTC); however, no change
address was specified.
""".strip(),
'mixed_inputs': """
NOTE: This transaction uses a mixture of both mmgen and non-mmgen inputs,
which makes the signing process more complicated.  When signing the
transaction, keys for the non-mmgen inputs must be supplied in a separate
file using the '-k' option to mmgen-txsign.

Selected mmgen inputs: %s"""
}

# Deleted text:
# Alternatively, you may import the mmgen keys into the wallet.dat of your
# offline bitcoind, first generating the required keys with mmgen-keygen and
# then running mmgen-txsign with the '-f' option to force the use of
# wallet.dat as the key source.


def connect_to_bitcoind():

	host,port,user,passwd = "localhost",8332,"rpcuser","rpcpassword"
	cfg = get_bitcoind_cfg_options((user,passwd))

	import mmgen.rpc.connection
	f = mmgen.rpc.connection.BitcoinConnection

	try:
		c = f(cfg[user],cfg[passwd],host,port)
	except:
		msg("Unable to establish RPC connection with bitcoind")
		sys.exit(2)

	return c


def trim_exponent(n):
	'''Remove exponent and trailing zeros.
	'''
	d = Decimal(n)
	return d.quantize(Decimal(1)) if d == d.to_integral() else d.normalize()



def is_btc_amt(amt):

	from decimal import Decimal
	try:
		ret = Decimal(amt)
	except:
		msg("%s: Invalid amount" % amt)
		return False

	if g.debug:
		print "Decimal(amt): %s\nAs tuple: %s" % (amt,repr(ret.as_tuple()))

	if ret.as_tuple()[-1] < -8:
		msg("%s: Too many decimal places in amount" % amt)
		return False

	if ret == 0:
		msg("Requested zero BTC amount")
		return False

	return trim_exponent(ret)

def check_btc_amt(amt):
	ret = is_btc_amt(amt)
	if ret:
		return ret
	else:
		sys.exit(3)


def get_bitcoind_cfg_options(cfg_keys):

	if "HOME" in os.environ:
		data_dir = ".bitcoin"
		cfg_file = "%s/%s/%s" % (os.environ["HOME"], data_dir, "bitcoin.conf")
	elif "HOMEPATH" in os.environ:
	# Windows:
		data_dir = r"Application Data\Bitcoin"
		cfg_file = "%s\%s\%s" % (os.environ["HOMEPATH"],data_dir,"bitcoin.conf")
	else:
		msg("Neither $HOME nor %HOMEPATH% are set")
		msg("Don't know where to look for 'bitcoin.conf'")
		sys.exit(3)

	try:
		f = open(cfg_file)
	except:
		msg("Unable to open file '%s' for reading" % cfg_file)
		sys.exit(2)

	cfg = {}

	for line in f.readlines():
		s = line.translate(None,"\n\t ").split("=")
		for k in cfg_keys:
			if s[0] == k: cfg[k] = s[1]

	f.close()

	for k in cfg_keys:
		if not k in cfg:
			msg("Configuration option '%s' must be set in %s" % (k,cfg_file))
			sys.exit(2)

	return cfg


def print_tx_to_file(tx,sel_unspent,send_amt,b2m_map,opts):
	tx_id = make_chksum_6(unhexlify(tx)).upper()
	outfile = "tx_%s[%s].raw" % (tx_id,send_amt)
	if 'outdir' in opts:
		outfile = "%s/%s" % (opts['outdir'], outfile)
	metadata = "%s %s %s" % (tx_id, send_amt, make_timestamp())
	data = "%s\n%s\n%s\n%s\n" % (
			metadata, tx,
			repr([i.__dict__ for i in sel_unspent]),
			repr(b2m_map)
		)
	write_to_file(outfile,data,confirm=False)
	msg("Transaction data saved to file '%s'" % outfile)


def print_signed_tx_to_file(tx,sig_tx,metadata,opts):
	tx_id = make_chksum_6(unhexlify(tx)).upper()
	outfile = "tx_{}[{}].sig".format(*metadata[:2])
	if 'outdir' in opts:
		outfile = "%s/%s" % (opts['outdir'], outfile)
	data = "%s\n%s\n" % (" ".join(metadata),sig_tx)
	write_to_file(outfile,data,confirm=False)
	msg("Signed transaction saved to file '%s'" % outfile)


def print_sent_tx_to_file(tx,metadata,opts):
	outfile = "tx_{}[{}].out".format(*metadata[:2])
	if 'outdir' in opts:
		outfile = "%s/%s" % (opts['outdir'], outfile)
	write_to_file(outfile,tx+"\n",confirm=False)
	msg("Transaction ID saved to file '%s'" % outfile)


def format_unspent_outputs_for_printing(out,sort_info,total):

	pfs  = " %-4s %-67s %-34s %-12s %-13s %-10s %s"
	pout = [pfs % ("Num","TX id,Vout","Address","MMgen ID",
		"Amount (BTC)","Age (days)", "Comment")]

	for n,i in enumerate(out):
		addr = "=" if i.skip == "addr" and "grouped" in sort_info else i.address
		tx = " " * 63 + "=" \
			if i.skip == "txid" and "grouped" in sort_info else str(i.txid)

		s = pfs % (str(n+1)+")", tx+","+str(i.vout),addr,i.mmid,i.amt,i.days,i.label)
		pout.append(s.rstrip())

	return \
"Unspent outputs ({} UTC)\nSort order: {}\n\n{}\n\nTotal BTC: {}\n".format(
		make_timestr(), " ".join(sort_info), "\n".join(pout), total
	)


def sort_and_view(unspent):

	def s_amt(i):   return i.amount
	def s_txid(i):  return "%s %03s" % (i.txid,i.vout)
	def s_addr(i):  return i.address
	def s_age(i):   return i.confirmations
	def s_mmgen(i): return i.account

	sort,group,show_mmaddr,reverse = "",False,False,False
	total = trim_exponent(sum([i.amount for i in unspent]))

	hdr_fmt   = "UNSPENT OUTPUTS (sort order: %s)  Total BTC: %s"

	options_msg = """
Sort options: [t]xid, [a]mount, a[d]dress, [A]ge, [r]everse, [M]mgen addr
Display options: [g]roup, show [m]mgen addr, r[e]draw screen
""".strip()
	prompt = \
"('q' = quit sorting, 'p' = print to file, 'v' = pager view, 'w' = wide view): "

	from copy import deepcopy
	print_to_file_msg = ""
	msg("")

	from mmgen.term import get_terminal_size

	max_acct_len = max([len(i.account) for i in unspent])

	while True:
		cols = get_terminal_size()[0]
		if cols < g.min_screen_width:
			msg("mmgen-txcreate requires a screen at least %s characters wide" %
					g.min_screen_width)
			sys.exit(2)

		addr_w = min(34+((1+max_acct_len) if show_mmaddr else 0),cols-46)
		tx_w = max(11,min(64, cols-addr_w-32))
		fs = " %-4s %-" + str(tx_w) + "s %-2s %-" + str(addr_w) + "s %-13s %-s"
		table_hdr = fs % ("Num","TX id  Vout","","Address",
							"Amount (BTC)","Age(d)")

		unsp = deepcopy(unspent)
		for i in unsp: i.skip = ""
		if group and (sort == "address" or sort == "txid"):
			for n in range(len(unsp)-1):
				a,b = unsp[n],unsp[n+1]
				if sort == "address" and a.address == b.address: b.skip = "addr"
				elif sort == "txid" and a.txid == b.txid:        b.skip = "txid"

		for i in unsp:
			amt = str(trim_exponent(i.amount))
			lfill = 3 - len(amt.split(".")[0]) if "." in amt else 3 - len(amt)
			i.amt = " "*lfill + amt
			i.days = int(i.confirmations * g.mins_per_block / (60*24))

			i.mmid,i.label = parse_mmgen_label(i.account)

			if i.skip == "addr":
				i.addr = "|" + "." * 33
			else:
				if show_mmaddr and i.mmid:
					acct_w   = min(max_acct_len, max(24,int(addr_w-10)))
					btaddr_w = addr_w - acct_w - 1

					dots = ".." if btaddr_w < len(i.address) else ""

					i.addr = "%s%s %s" % (
						i.address[:btaddr_w-len(dots)],
						dots,
						i.account[:acct_w])
				else:
					i.addr = i.address

			dots = "..." if tx_w < 64 else ""
			i.tx = " " * (tx_w-4) + "|..." if i.skip == "txid" \
					else i.txid[:tx_w-len(dots)]+dots

		sort_info = ["reverse"] if reverse else []
		sort_info.append(sort if sort else "unsorted")
		if group and (sort == "address" or sort == "txid"):
			sort_info.append("grouped")

		out = [hdr_fmt % (" ".join(sort_info), total), table_hdr]

		for n,i in enumerate(unsp):
			out.append(fs % (str(n+1)+")",i.tx,i.vout,i.addr,i.amt,i.days))

		msg("\n".join(out) +"\n\n" + print_to_file_msg + options_msg)
		print_to_file_msg = ""

		immed_chars = "atdAMrgmeqpvw"
		skip_prompt = False

		while True:
			reply = get_char(prompt, immed_chars=immed_chars)

			if   reply == 'a': unspent.sort(key=s_amt);  sort = "amount"
			elif reply == 't': unspent.sort(key=s_txid); sort = "txid"
			elif reply == 'd': unspent.sort(key=s_addr); sort = "address"
			elif reply == 'A': unspent.sort(key=s_age);  sort = "age"
			elif reply == 'M':
				unspent.sort(key=s_mmgen); sort = "mmgen"
				show_mmaddr = True
			elif reply == 'r':
				unspent.reverse()
				reverse = False if reverse else True
			elif reply == 'g': group = False if group else True
			elif reply == 'm': show_mmaddr = False if show_mmaddr else True
			elif reply == 'e': pass
			elif reply == 'q': pass
			elif reply == 'p':
				data = format_unspent_outputs_for_printing(unsp,sort_info,total)
				outfile = "listunspent[%s].out" % ",".join(sort_info)
				write_to_file(outfile, data)
				print_to_file_msg = "Data written to '%s'\n\n" % outfile
			elif reply == 'v':
				do_pager("\n".join(out))
				continue
			elif reply == 'w':
				data = format_unspent_outputs_for_printing(unsp,sort_info,total)
				do_pager(data)
				continue
			else:
				msg("\nInvalid input")
				continue

			break

		msg("\n")
		if reply == 'q': break

	return tuple(unspent)


def parse_mmgen_label(s,check_label_len=False):

	if not s: return "",""

	try:    w1,w2 = s.split(None,1)
	except: w1,w2 = s,""

	if not is_mmgen_addr(w1): return "",w1
	if check_label_len: check_addr_label(w2)
	return w1,w2


def view_tx_data(c,inputs_data,tx_hex,b2m_map,metadata=[],pager=False):

	td = c.decoderawtransaction(tx_hex)

	out = "TRANSACTION DATA\n\n"

	if metadata:
		out += "Header: [Tx ID: {}] [Amount: {} BTC] [Time: {}]\n\n".format(*metadata)

	out += "Inputs:\n\n"
	total_in = 0
	for n,i in enumerate(td['vin']):
		for j in inputs_data:
			if j['txid'] == i['txid'] and j['vout'] == i['vout']:
				days = int(j['confirmations'] * g.mins_per_block / (60*24))
				total_in += j['amount']
				addr = j['address']

				if j['account']:
					tmp = j['account'].split(None,1)
					mmid,label = tmp if len(tmp) == 2 else (tmp[0],"")
					label = label or ""
				else:
					mmid,label = "",""

				mmid_str = ((34-len(addr))*" " + " (%s)" % mmid) if mmid else ""

				for d in (
	(n+1, "tx,vout:",       "%s,%s" % (i['txid'], i['vout'])),
	("",  "address:",       addr + mmid_str),
	("",  "label:",         label),
	("",  "amount:",        "%s BTC" % trim_exponent(j['amount'])),
	("",  "confirmations:", "%s (around %s days)" % (j['confirmations'], days))
					):
					if d[2]: out += ("%3s %-8s %s\n" % d)
				out += "\n"

				break
	total_out = 0
	out += "Outputs:\n\n"
	for n,i in enumerate(td['vout']):
		addr = i['scriptPubKey']['addresses'][0]
		mmid,label = b2m_map[addr] if addr in b2m_map else ("","")
		mmid_str = ((34-len(addr))*" " + " (%s)" % mmid) if mmid else ""
		total_out += i['value']
		for d in (
				(n+1, "address:",  addr + mmid_str),
				("",  "label:",    label),
				("",  "amount:",   trim_exponent(i['value']))
			):
			if d[2]: out += ("%3s %-8s %s\n" % d)
		out += "\n"

	out += "Total input:  %s BTC\n" % trim_exponent(total_in)
	out += "Total output: %s BTC\n" % trim_exponent(total_out)
	out += "TX fee:       %s BTC\n" % trim_exponent(total_in-total_out)

	if pager: do_pager(out)
	else:     msg("\n"+out)


def parse_tx_data(tx_data,infile):

	if len(tx_data) != 4:
		msg("'%s': not a transaction file" % infile)
		sys.exit(2)

	err_fmt = "Transaction %s is invalid"

	if len(tx_data[0].split()) != 3:
		msg(err_fmt % "metadata")
		sys.exit(2)

	try: unhexlify(tx_data[1])
	except:
		msg(err_fmt % "hex data")
		sys.exit(2)
	else:
		if not tx_data:
			msg("Transaction is empty!")
			sys.exit(2)

	try:
		inputs_data = eval(tx_data[2])
	except:
		msg(err_fmt % "inputs data")
		sys.exit(2)
	else:
		if not inputs_data:
			msg("Transaction has no inputs!")
			sys.exit(2)

	try:
		map_data = eval(tx_data[3])
	except:
		msg(err_fmt % "mmgen to btc address map data")
		sys.exit(2)

	return tx_data[0].split(),tx_data[1],inputs_data,map_data


def select_outputs(unspent,prompt):

	while True:
		reply = my_raw_input(prompt,allowed_chars="0123456789 -").strip()

		if not reply: continue

		from mmgen.util import parse_address_list
		selected = parse_address_list(reply,sep=None)

		if not selected: continue

		if selected[-1] > len(unspent):
			msg("Inputs must be less than %s" % len(unspent))
			continue

		return selected

def is_mmgen_seed(s):
	import re
	return len(s) == 8 and re.match(r"^[0123456789ABCDEF]*$",s)

def is_mmgen_num(s):
	import re
	return len(s) <= g.mmgen_idx_max_digits \
		and re.match(r"^[123456789]+[0123456789]*$",s)

def is_mmgen_addr(s):
	import re
	return len(s) > 9 and s[8] == ':' \
		and re.match(r"^[0123456789ABCDEF]*$",s[:8]) \
		and len(s[9:]) <= g.mmgen_idx_max_digits \
		and re.match(r"^[123456789]+[0123456789]*$",s[9:])

def is_btc_addr(s):
	from mmgen.bitcoin import verify_addr
	return verify_addr(s)


def btc_addr_to_mmgen_addr(btc_addr,b2m_map):
	if btc_addr in b2m_map:
		return b2m_map[btc_addr]
	return "",""


def mmgen_addr_to_walletd(c,mmaddr,acct_data):

	# We don't want to create a new object, so we'll use append()
	if not acct_data:
		for i in c.listaccounts():
			acct_data.append(i)

	for a in acct_data:
		if not a: continue
		try:
			w1,w2 = a.split(None,1)
		except:
			w1,w2 = a,""
		if w1 == mmaddr:
			acct = a
			break
	else:
		return "",""

	alist = c.getaddressesbyaccount(acct)

	if len(alist) != 1:
		msg("""
ERROR: More than one address found for account: "%s".
The tracking "wallet.dat" file appears to have been altered by a non-%s
program.  Please restore "wallet.dat" from a backup or create a new wallet
and re-import your addresses.
""".strip() % (acct,g.proj_name_cap))
		sys.exit(3)

	return alist[0],w2


def mmgen_addr_to_addr_data(m,addr_data):

	no_data_msg = """
No data found for MMgen address '%s'. Please import this address into
your tracking wallet, or supply an address file for it on the command line.
""".strip() % m
	warn_msg = """
Warning: no data for address '%s' exists in the wallet, so it was
taken from the user-supplied address file.  You're strongly advised to
import this address into your tracking wallet before proceeding with
this transaction.  The address will not be tracked until you do so.
""".strip() % m
	fail_msg = """
No data found for MMgen address '%s' in either wallet or supplied
address file.  Please import this address into your tracking wallet, or
supply an address file for it on the command line.
""".strip() % m

	ID,num = m.split(":")
	from binascii import unhexlify
	try: unhexlify(ID)
	except: pass
	else:
		try: num = int(num)
		except: pass
		else:
			if not addr_data:
				msg(no_data_msg)
				sys.exit(2)
			for i in addr_data:
				if ID == i[0]:
					for j in i[1]:
						if j[0] == num:
							msg(warn_msg)
							if not user_confirm("Continue anyway?"):
								sys.exit(1)
							return j[1],(j[2] if len(j) == 3 else "")
			msg(fail_msg)
			sys.exit(2)

	msg("Invalid format: %s" % m)
	sys.exit(3)


def check_mmgen_to_btc_addr_mappings(inputs_data,b2m_map,infiles,seeds,opts):
	in_maplist = [(i['account'].split()[0],i['address'])
		for i in inputs_data if i['account']
			and is_mmgen_addr(i['account'].split()[0])]
	out_maplist = [(i[1][0],i[0]) for i in b2m_map.items()]

	for maplist,label in (in_maplist,"inputs"), (out_maplist,"outputs"):
		if not maplist: continue
		qmsg("Checking MMGen -> BTC address mappings for %s" % label)
		mmaddrs = [i[0] for i in maplist]
		from copy import deepcopy
		pairs = get_keys_for_mmgen_addrs(mmaddrs,
				deepcopy(infiles),seeds,opts,gen_pairs=True)
		for a,b in zip(sorted(pairs),sorted(maplist)):
			if a != b:
				msg("""
MMGen -> BTC address mappings differ!
In transaction:      %s
Generated from seed: %s
	""".strip() % (" ".join(a)," ".join(b)))
				sys.exit(3)

	qmsg("Address mappings OK")


def check_addr_label(label):

	if len(label) > g.max_addr_label_len:
		msg("'%s': overlong label (length must be <=%s)" %
				(label,g.max_addr_label_len))
		sys.exit(3)

	for ch in label:
		if ch not in g.addr_label_symbols:
			msg("""
"%s": illegal character in label "%s".
Only ASCII printable characters are permitted.
""".strip() % (ch,label))
			sys.exit(3)


def parse_addrs_file(f):

	lines = get_lines_from_file(f,"address data",remove_comments=True)

	try:
		seed_id,obrace = lines[0].split()
	except:
		msg("Invalid first line: '%s'" % lines[0])
		sys.exit(3)

	cbrace = lines[-1]

	if   obrace != '{':
		msg("'%s': invalid first line" % lines[0])
	elif cbrace != '}':
		msg("'%s': invalid last line" % cbrace)
	elif not is_mmgen_seed(seed_id):
		msg("'%s': invalid Seed ID" % seed_id)
	else:
		ret = []
		for i in lines[1:-1]:
			d = i.split(None,2)

			if not is_mmgen_num(d[0]):
				msg("'%s': invalid address num. in line: %s" % (d[0],d))
				sys.exit(3)

			if not is_btc_addr(d[1]):
				msg("'%s': invalid Bitcoin address" % d[1])
				sys.exit(3)

			if len(d) == 3:
				check_addr_label(d[2])

			ret.append(tuple(d))

		return seed_id,ret

	sys.exit(3)


def sign_transaction(c,tx_hex,sig_data,keys=None):

	if keys:
		qmsg("%s keys total" % len(keys))
		if g.debug: print "Keys:\n  %s" % "\n  ".join(keys)

	msg_r("Signing transaction...")
	from mmgen.rpc import exceptions
	try:
		sig_tx = c.signrawtransaction(tx_hex,sig_data,keys)
	except exceptions.InvalidAddressOrKey:
		msg("failed\nInvalid address or key")
		sys.exit(3)

	return sig_tx


def get_keys_for_mmgen_addrs(mmgen_addrs,infiles,seeds,opts,gen_pairs=False):

	seed_ids = list(set([i[:8] for i in mmgen_addrs]))
	seed_ids_save = seed_ids[0:]  # deep copy
	ret = []

	seeds_keys = [i for i in seed_ids if i in seeds]

	while seed_ids:
		if seeds_keys:
			seed = seeds[seeds_keys.pop(0)]
		else:
			infile = False
			if infiles:
				infile = infiles.pop(0)
				seed = get_seed_retry(infile,opts)
			elif "from_brain" in opts or "from_mnemonic" in opts \
				or "from_seed" in opts or "from_incog" in opts:
				msg("Need data for seed ID %s" % seed_ids[0])
				seed = get_seed_retry("",opts)
			else:
				b,p,v = ("A seed","","is") if len(seed_ids) == 1 \
						else ("Seed","s","are")
				msg("ERROR: %s source%s %s required for the following seed ID%s: %s"%
						(b,p,v,p," ".join(seed_ids)))
				sys.exit(2)

		seed_id = make_chksum_8(seed)
		if seed_id in seed_ids:
			seed_ids.remove(seed_id)
			addr_ids = [int(i[9:]) for i in mmgen_addrs if i[:8] == seed_id]
			seeds[seed_id] = seed
			from mmgen.addr import generate_keys,generate_addrs
			if gen_pairs:
				o = {"gen_what":"addresses"}
				ret += [("%s:%s" % (seed_id,i['num']),i['addr'])
					for i in generate_addrs(seed, addr_ids, o)]
			else:
				ret += [i['wif'] for i in generate_keys(seed, addr_ids)]
		else:
			if seed_id in seed_ids_save:
				msg_r("Ignoring duplicate seed source")
				if infile: msg(" '%s'" % infile)
				else:      msg(" for ID %s" % seed_id)
			else:
				msg("Seed source produced an invalid seed ID (%s)" % seed_id)
				if "from_incog" in opts or infile.split(".")[-1] == g.incog_ext:
					msg(
"""Incorrect hash preset, password or incognito wallet data

Trying again...""")
					infiles.insert(0,infile) # ugly!
				elif infile:
					msg("Invalid input file '%s'" % infile)
					sys.exit(2)

	return ret


def sign_tx_with_bitcoind_wallet(c,tx_hex,sig_data,keys,opts):

	try:
		sig_tx = sign_transaction(c,tx_hex,sig_data,keys)
	except:
		from mmgen.rpc import exceptions
		msg("Using keys in wallet.dat as per user request")
		prompt = "Enter passphrase for bitcoind wallet: "
		while True:
			passwd = get_bitcoind_passphrase(prompt,opts)

			try:
				c.walletpassphrase(passwd, 9999)
			except exceptions.WalletPassphraseIncorrect:
				msg("Passphrase incorrect")
			else:
				msg("Passphrase OK"); break

		sig_tx = sign_transaction(c,tx_hex,sig_data,keys)

		msg("Locking wallet")
		try:
			c.walletlock()
		except:
			msg("Failed to lock wallet")

	return sig_tx


def preverify_keys(addrs_orig, keys_orig):

	addrs,keys,wrong_keys = set(addrs_orig[0:]),set(keys_orig[0:]),[]

	if len(keys) < len(addrs):
		msg("ERROR: not enough keys (%s) for number of non-%s addresses (%s)" %
				(len(keys),g.proj_name_cap,len(addrs)))
		sys.exit(2)

	import mmgen.bitcoin as b

	qmsg_r('Checking that user-supplied key list contains valid keys...')

	invalid_keys = []

	for n,k in enumerate(keys,1):
		c = False if k[0] == '5' else True
		if b.wiftohex(k,compressed=c) == False:
			invalid_keys.append(k)

	if invalid_keys:
		s = "" if len(invalid_keys) == 1 else "s"
		msg("\n%s/%s invalid key%s in keylist!\n" % (len(invalid_keys),len(keys),s))
		sys.exit(2)
	else: qmsg("OK")

	msg('Pre-verifying keys in user-supplied key list (Ctrl-C to skip)')

	try:
		for n,k in enumerate(keys,1):
			msg_r("\rkey %s of %s" % (n,len(keys)))
			c = False if k[0] == '5' else True
			hexkey = b.wiftohex(k,compressed=c)
			addr = b.privnum2addr(int(hexkey,16),compressed=c)
			if addr in addrs:
				addrs.remove(addr)
				if not addrs: break
			else:
				wrong_keys.append(k)
	except KeyboardInterrupt:
		msg("\nSkipping")
	else:
		msg("")
		if wrong_keys:
			s = "" if len(wrong_keys) == 1 else "s"
			msg("%s extra key%s found" % (len(wrong_keys),s))

		if addrs:
			s = "" if len(addrs) == 1 else "es"
			msg("No keys found for the following non-%s address%s:" %
					(g.proj_name_cap,s))
			print "  %s" % "\n  ".join(addrs)
			sys.exit(2)


def missing_keys_errormsg(other_addrs):
	msg("""
A key file must be supplied (or use the "-w" option) for the following
non-mmgen address%s:
""".strip() % ("" if len(other_addrs) == 1 else "es"))
	print "  %s" % "\n  ".join([i['address'] for i in other_addrs])