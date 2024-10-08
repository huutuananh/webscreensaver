#!/usr/bin/env python3

"""
    WebScreensaver - Make any web page a screensaver
    Copyright (C) 2012-2017  Lucas Martin-King & Thomas Reifenberger

    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 2 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License along
    with this program; if not, write to the Free Software Foundation, Inc.,
    51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
"""

import logging
import os
import pathlib
import random
import signal
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkX11", "3.0")
gi.require_version("WebKit2", "4.1")

from gi.repository import Gdk, GdkX11, GObject, Gtk
from gi.repository import WebKit2 as WebKit

# Tạo logger
logger = logging.getLogger("webscreensaver")
logger.setLevel(logging.ERROR)  # Thiết lập mức độ log

# Tạo file handler
handler = logging.FileHandler("xscreensaver.log")
handler.setLevel(logging.ERROR)  # Thiết lập mức độ log cho handler

# Tạo formatter
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# Thêm formatter vào handler
handler.setFormatter(formatter)

# Thêm handler vào logger
logger.addHandler(handler)


class WebScreensaver(object):
    """
    A simple wrapper for WebKit which works as an XScreensaver Hack
    """

    def __init__(
        self,
        url="https://www.google.com",
        window_id=None,
        scripts=None,
        cookie_file=None,
        disk_cache=True,
    ):
        self.window_id = window_id
        self.scripts = scripts
        self.url = url
        self.cookie_file = cookie_file
        self.disk_cache = disk_cache

        self.w = 640
        self.h = 480

    def setup_window(self):
        """Perform some magic (if needed) to set up a Gtk window"""
        if self.window_id:
            self.win = Gtk.Window(type=Gtk.WindowType.POPUP)

            gdk_display = GdkX11.X11Display.get_default()
            self.gdk_win = GdkX11.X11Window.foreign_new_for_display(
                gdk_display, self.window_id
            )

            # We show the window so we get a Gdk Window,
            # then we we can reparent it...
            self.win.show()
            # self.win.get_window().reparent(self.gdk_win, 0, 0)

            x, y, w, h = self.gdk_win.get_geometry()
            logger.info(f"Get geometry: {x}, {y}, {w}, {h}")

            # Make us cover our parent window
            self.win.move(0, 0)
            self.win.set_default_size(w, h)
            self.win.set_size_request(w, h)
            # self.win.fullscreen()

            self.w, self.h = w, h
        else:
            self.win = Gtk.Window()
            self.win.set_default_size(self.w, self.h)
            self.win.move(0, 0)

    def setup_browser(self):
        """Sets up WebKit in our window"""
        self.browser = WebKit.WebView()

        settings = self.browser.get_settings()

        # Try to enable webgl
        try:
            settings.set_enable_webgl(True)
        except Exception as err:
            print("Could not enable WebGL: {}".format(err))

        # Enable disk caching
        if self.disk_cache:
            context = self.browser.get_context()
            data_manager = context.get_website_data_manager()
            context.set_cache_model(WebKit.CacheModel.WEB_BROWSER)
            print("Cache directory:", data_manager.props.disk_cache_directory)

        # Take a stab at guessing whether we are running in the
        # XScreensaver preview window...
        if self.w < 320 and self.h < 240:
            self.browser.set_full_content_zoom(True)
            self.browser.set_zoom_level(0.4)

        self.browser.set_size_request(self.w, self.h)

        # self.browser.connect("load-changed", self.handle_load_changed)

    def setup_cookie_jar(self):
        if self.cookie_file:
            context = self.browser.get_context()
            cookie_manager = context.get_cookie_manager()
            cookie_manager.set_accept_policy(WebKit.CookieAcceptPolicy.ALWAYS)
            cookie_manager.set_persistent_storage(
                self.cookie_file, WebKit.CookiePersistentStorage.TEXT
            )

    def handle_load_changed(self, view, load_event: WebKit.LoadEvent):
        print("Load changed:", view, load_event)

        if load_event == WebKit.LoadEvent.FINISHED:
            self.handle_on_load(view)

    def handle_on_load(self, view):
        """
        Handler for browser page load events.
        This will be executed for every frame within the browser.
        """

        if not self.scripts:
            return

        for script in self.scripts:
            print("Executing script: ", script)
            self.browser.run_javascript(script, None, None, None)

    def setup_layout(self):
        """Make sure the browser can expand without affecting the window"""
        sw = Gtk.Layout()
        sw.put(self.browser, 0, 0)
        self.win.add(sw)

    def setup(self):
        """Do all the things!"""
        self.setup_window()
        self.setup_browser()
        self.setup_layout()
        self.setup_cookie_jar()

        def terminate(*args):
            Gtk.main_quit()

        self.win.connect("destroy", terminate)
        self.win.connect("delete-event", terminate)

        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, terminate)

        self.win.show_all()

        self.browser.load_uri(self.url)

    @classmethod
    def determine_window_id(cls, win_id=None):
        """Try and get an XID to use as our parent window"""
        if not win_id:
            win_id = os.getenv("XSCREENSAVER_WINDOW")

        if win_id:
            win_id = int(win_id, 16)

        logger.info(f"Get window id: {win_id}")
        return win_id


class UserScripts(object):
    """
    Some quick and dirty scripts to help us remove cruft from web pages
    """

    @classmethod
    def remove_ids(cls, _id):
        script = """
            (function() {
                var el = document.getElementById("%s");
                if (el) {
                    el.parentNode.removeChild(el);
                }
            })();
        """
        return script % _id

    @classmethod
    def remove_tags(cls, tag):
        script = """
            (function() {
                var tags = document.getElementsByTagName("%s");
                if (tags && tags.length > 0) {
                    for (var i = 0; i < tags.length; i++) {
                        var el = tags[i];
                        el.parentNode.removeChild(el);
                    }
                }
            })();
        """
        return script % tag

    @classmethod
    def inject_css(cls, css_str):
        script = """
            (function() {
                var node = document.createElement('style');
                node.innerHTML = "%s";
                document.body.appendChild(node);
            })();
        """
        return script % css_str


class WebHacks(object):
    """
    A collection of neat HTML5/WebGL demos
    """

    class Hack(object):
        __slots__ = "name url scripts".split(" ")

        def __init__(self, name, url=None, scripts=None):
            self.name, self.url, self.scripts = name, url, scripts

    hacks = (
        Hack(
            "starfield",
            url="http://www.chiptune.com/starfield/starfield.html",
            scripts=[UserScripts.remove_tags("iframe")],
        ),
        Hack(
            "reactive-ball",
            url="https://web.archive.org/web/20181207122336/lab.aerotwist.com/webgl/reactive-ball/",
            scripts=[
                UserScripts.remove_ids("msg"),
                UserScripts.remove_ids("wm-ipp-base"),
            ],
        ),
        Hack(
            "hatching-glow",
            url="http://www.ro.me/tech/demos/1/index.html",
            scripts=[UserScripts.remove_ids("info")],
        ),
        Hack(
            "shadow-map",
            url="https://alteredqualia.com/three/examples/webgl_shadowmap.html",
            scripts=[UserScripts.remove_ids("info")],
        ),
        Hack(
            "sechelt",
            url="https://mixedreality.mozilla.org/sechelt/",
            scripts=[UserScripts.remove_ids("enterVr")],
        ),
        Hack(
            "cyber-auroras",
            url="https://js1k.com/2018-coins/demo/3076",
            scripts=[
                UserScripts.remove_tags("header"),
                UserScripts.inject_css(
                    "iframe { padding: 0 !important; } body { background: black; }"
                ),
            ],
        ),
        Hack(
            "jellyfish",
            url="https://akirodic.com/p/jellyfish/",
            scripts=[UserScripts.inject_css("#console { display: none; }")],
        ),
        Hack("gimme-shiny", url="https://gimmeshiny.com/?seconds=30"),
        Hack("cell-shader", url="http://www.ro.me/tech/demos/6/index.html"),
        Hack("kinect", url="https://mrdoob.com/lab/javascript/webgl/kinect/"),
        Hack("conductor", url="http://www.mta.me/"),
        Hack(
            "flying-toasters",
            url="https://bryanbraun.github.io/after-dark-css/all/flying-toasters.html",
        ),
    )

    @classmethod
    def items(cls):
        return list(cls.hacks)

    @classmethod
    def print_list(cls):
        for hack in cls.hacks:
            print("%15s\t%s" % (hack.name, hack.url))

    @classmethod
    def load_from_file(cls, file_path):
        try:
            import toml
        except ImportError:
            raise Exception(
                "Could not import `toml`, you probably need to install it via `pip install toml`"
            )

        cfg = toml.load(open(file_path, "r"))

        hacks = [cls.hack_from_config(site, section) for (site, section) in cfg.items()]

        cls.hacks = [h for h in hacks if h]

    @classmethod
    def hack_from_config(cls, site, section):
        if "url" not in section:
            print(f"Error: `url` not found in section for site `{site}`. Skipping.")
            return

        action_map = {
            "inject_css": UserScripts.inject_css,
            "remove_ids": UserScripts.remove_ids,
            "remove_tags": UserScripts.remove_tags,
        }

        url = section["url"]

        actions = section.keys() & action_map.keys()

        scripts = []
        for act in actions:
            params = section[act]
            if not isinstance(params, list):
                params = [params]
            for param in params:
                script = action_map[act](param)
                scripts.append(script)

        return WebHacks.Hack(name=site, url=url, scripts=scripts)

    @classmethod
    def determine_screensaver(cls, name=None):
        for hack in cls.hacks:
            if hack.name == name:
                return hack

        # I'm feeling lucky :-)
        return random.choice(cls.hacks)


class Cycler:
    def __init__(self, state_file):
        self.state_file = state_file

    def save_state(self, item):
        with open(self.state_file, "w") as f:
            f.write(f"{item}")
            f.flush()

    def load_state(self):
        try:
            with open(self.state_file, "r") as f:
                item = f.read().strip()
                return item
        except:
            return None

    def determine_item(self, item_list):
        item = self.load_state()
        if item is None:
            return item_list[0]
        try:
            idx = item_list.index(item)
            return item_list[idx + 1]
        except (IndexError, ValueError):
            return item_list[0]


if __name__ == "__main__":
    import argparse

    # Sử dụng logger
    logger.info("Start webscreensaver.py")

    parser = argparse.ArgumentParser(
        description="WebScreensaver: Run a web page as your screensaver"
    )
    parser.add_argument("-window-id", help="XID of Window to draw on")
    parser.add_argument(
        "--window-id", help="XID of Window to draw on"
    )  # Some XScreensaver versions use this
    parser.add_argument("-url", help="URL of page to display")
    parser.add_argument("-choose", help="Select a favourite")
    parser.add_argument(
        "-cycle",
        action="store_true",
        help="Cycle to the next creensaver from the list (each time when run)",
    )
    parser.add_argument("-list", action="store_true", help="List favourites")
    parser.add_argument(
        "-sites-list", type=str, help="List of sites to use instead of built-in list"
    )
    parser.add_argument("-cookie-file", metavar="PATH", help="Store cookies in PATH")
    parser.add_argument(
        "-no-cache", action="store_true", help="Disable disk caching of website data"
    )
    args = parser.parse_args()

    if args.sites_list:
        WebHacks.load_from_file(args.sites_list)

    if args.list:
        WebHacks.print_list()
        sys.exit(0)

    url, scripts = None, None

    if args.url:
        url = args.url
        logger.info(f"Get url: {args.url}")
    elif args.cycle:
        cache_dir = (
            pathlib.Path(
                os.environ.get("XDG_CACHE_HOME") or (pathlib.Path.home() / ".cache")
            )
            / "webscreensaver"
        )
        cycle_file = cache_dir / "cycle_state"
        cycle = Cycler(cycle_file)
        item_map = {x.name: x for x in WebHacks.items()}
        item = cycle.determine_item([x.name for x in WebHacks.items()])
        cycle.save_state(item)
        hack = item_map[item]
        url, scripts = hack.url, hack.scripts
    else:
        hack = WebHacks.determine_screensaver(args.choose)
        url, scripts = hack.url, hack.scripts

    saver = WebScreensaver(
        url=url,
        window_id=WebScreensaver.determine_window_id(args.window_id),
        scripts=scripts,
        cookie_file=args.cookie_file,
        disk_cache=not args.no_cache,
    )
    saver.setup()

    Gtk.main()
