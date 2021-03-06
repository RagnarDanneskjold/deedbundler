# -*- coding: utf-8 -*-
###
# Copyright (c) 2014, punkman
# All rights reserved.
#
###
import time
import json
from getpass import getpass

import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
import supybot.schedule as schedule
import supybot.ircmsgs as ircmsgs

from deedbundler import raw_pastebin
from deedbundler.core import Bundler


class DeedSystem(callbacks.Plugin):
    """DeedSystem plugin"""
    #threaded = True

    def __init__(self, irc):
        self.__parent = super(DeedSystem, self)
        self.__parent.__init__(irc)
        
        # load deeds config
        config_path = self.registryValue('configPath')
	with open(config_path,'r') as f:
		deeds_config = json.loads(f.read())

        # prompt for password
        pwd = getpass('Enter wallet password:')
        deeds_config['wallet_pass'] = pwd

        # start the bundler
        self.deeds = Bundler(deeds_config)
        self.deeds.setup()

        # schedule events
        def make_bundle():
            self._make_bundle(irc)

        def confirm_bundle():
            self._confirm_bundle(irc)

        schedule.addPeriodicEvent(make_bundle, deeds_config['make_bundle_interval'], now=False, name='make_bundle')
        schedule.addPeriodicEvent(confirm_bundle, deeds_config['confirm_bundle_interval'], now=False, name='confirm_bundle')

    def die(self):
        try:
            schedule.removeEvent('make_bundle')
            schedule.removeEvent('confirm_bundle')
        except:
            pass

        self.deeds.shutdown()
        self.__parent.die()

    ## COMMANDS

    def deed(self, irc, msg, args, url):
        """[url]

        the bot will search [url] for signed deeds and queue them.
        """

        # converts pastebin URLs to raw
        url = raw_pastebin(url)
        try:
            content = utils.web.getUrl(url, size=self.deeds.config['max_url_size'])
        except utils.web.Error as e:
            txt = 'Error fetching URL. ({0})'.format(str(e))
            irc.reply(txt)
            return

        num_valid, errors = self.deeds.save_deeds(content)
        
        if num_valid == 0:
            txt = 'No valid deeds found, try again.'
        else:
            _deeds = 'deed' if num_valid == 1 else 'deeds'
            txt = 'Queued {0} valid {1} for next bundle.'.format(num_valid, _deeds)

        debug = []
        for k in errors:
            if errors[k] > 0:
                debug.append('{0}: {1}'.format(k, errors[k]))
        if debug: 
            txt += ' ({0})'.format(' | '.join(debug))

        irc.reply(txt)

    deed = wrap(deed, ['public', 'httpUrl'])


    def balance(self, irc, msg, args):
        """ returns bot balance"""
        data = self.deeds.main_balance()
        confirmed = data[0] / 100000000.0
        unconfirmed = data[1] / 100000000.0
        enough  = self.deeds.num_bundles_left()
        txt = 'Balance at {0} is {1} BTC ({2} unconfirmed), enough for {3} more bundles.'
        txt = txt.format(self.deeds.config['main_address'], confirmed, unconfirmed, enough)
        irc.reply(txt)

    balance = wrap(balance, ['public'])


    def status(self, irc, msg, args):
        """ returns bot status"""
        pending, last_bundle, unconfirmed = self.deeds.status()
        pending = 'No' if pending == 0 else pending
        _deeds = 'deed' if pending == 1 else 'deeds'
        now = int(time.time())
        ago = utils.timeElapsed(now - last_bundle, weeks=False, seconds=False, short=True) if last_bundle else 'n/a'
        txt = '{0} pending {1} | Last bundle {2} ago'.format(pending, _deeds, ago)
    
        if unconfirmed:
            _bundles = 'bundle' if unconfirmed == 1 else 'bundles'
            txt += ' | {0} unconfirmed {1}'.format(unconfirmed, _bundles)

        irc.reply(txt)

    status = wrap(status, ['public'])


    def _make_bundle(self, irc):
        print 'make: start'
        try:
            success, msg = self.deeds.make_bundle()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            print e
        print 'make: {0}'.format(msg)

        if success:
            num, address = msg
            deeds = 'deed' if num == 1 else 'deeds'
            url = self._bundle_url(address, short=True, length=8)
            txt = 'Bundled {0} {1} | {2}'.format(num, deeds, url)
            # announce bundle
            for channel in irc.state.channels:
                msg = ircmsgs.privmsg(channel, txt)
                irc.queueMsg(msg)

    def _confirm_bundle(self, irc):
        try:
            success, msg = self.deeds.confirm_bundle()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            print e
     
        if success:
            address, txid = msg
            url = self._bundle_url(address, short=True, length=8)
            txt = 'Confirmed bundle {0} | {1}'.format(address, url)
            # announce bundle
            for channel in irc.state.channels:
                msg = ircmsgs.privmsg(channel, txt)
                irc.queueMsg(msg)

        if msg != 'no_unconfirmed' and msg != 'waiting_for_confirm':
            print 'confirm: {0}'.format(msg)

    def _bundle_url(self, address, short=False, length=None):
        host = self.deeds.config['hostname']
        path = 'bundle' if not short else 'b'
        addr = address if length is None else address[:length]
        url = 'http://{0}/{1}/{2}'.format(host, path, addr)
        return url

    def _deed_url(self, deed_hash, short=False, length=None):
        host = self.deeds.config['hostname']
        path = 'deed' if not short else 'd'
        dhash = deed_hash if length is None else deed_hash[:length]
        url = 'http://{0}/{1}/{2}'.format(host, path, dhash)
        return url

Class = DeedSystem


# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
