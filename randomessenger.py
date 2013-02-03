#!/usr/bin/env python
""" this is a chat client, it connect automatically to the server,
but if you have open port on your firewall/router you can receive connection from other clients"""

import sys, os
import pygtk, gtk, gobject
if os.name == 'posix':
    import pygst
    pygst.require("0.10")
    import gst

import threading
import select
import errno
import Queue
import socket
from socket import AF_INET, SOCK_STREAM

SERVER = '192.168.1.3'
LOCAL_HOST = '' # Symbolic name meaning all available interfaces
CHAT_PORT = 5000 # Arbitrary non-privileged port
VIDEO_PORT = 5001


class NewMessageSignal(gobject.GObject):
    def __init__(self):
        self.__gobject_init__()

class Receiver(threading.Thread):
    def __init__(self,new_message_signal):
        threading.Thread.__init__(self)
        self.running = True
        self.client_mode = False
        self.server_mode = False

        self.new_message_signal = new_message_signal        
        self.sock = socket.socket(AF_INET,SOCK_STREAM)
        
        #listening for connections from other clients
        #self.sock.bind((LOCAL_HOST, CHAT_PORT))
        #self.sock.listen(1)

    def run(self):
        #now = datetime.datetime.now()
        timeout = 1
        self.inputs = [self.sock]
        self.outputs = []

        self.connection = None
        self.new_message_signal.emit('sys_message', 'Listening for connections...')
        self.connect(SERVER) #gestire eccezioni

        while self.running:
            try:
                readable, writable, exceptional = select.select(self.inputs, self.outputs, self.inputs, timeout)
            except select.error, ex:
                if ex[0] == errno.EBADF:
                    print("il server si e' disconnesso?")
                    self.sock.close()
                    self.running = False
                return
            for s in readable:
                if s is self.sock:
                    if self.server_mode == False and self.client_mode == False: #ovvero siamo in attesa, non connessi
                        #disconnettersi dal server, o avvisare
                        self.connection, self.client_address = s.accept()
                        #connection.setblocking(0)
                        self.inputs.append(self.connection)
                        self.client_mode == True
                        self.new_message_signal.emit('sys_message', 'Connection established with '+ self.client_address[0])
                        print('We are in server mode')

                        # Give the connection a queue for data we want to send
                        #message_queues[connection] = Queue.Queue()
                    else:
                        #data from our connection
                        print('message')
                        try:
                            data = s.recv(1024)
                        except socket.error:
                            #alone                            
                            pass

                        if data:
                            message = data.decode('utf-8')
                            if message[:6] == '/sysme':
                                self.new_message_signal.emit('sys_message', message[7:])
                            else:
                                self.new_message_signal.emit('new_message', message)
                        else:
                            print('no data from the server')
                            s.close()
                else:
                    #another sock? another connection?
                    try:
                        data = s.recv(1024)
                        if data:
                            print('message from server')
                            message = data.decode('utf-8')
                            if message == '/sys alone':
                                self.new_message_signal.emit('sys_message', 'You are alone on the server, wait or go')
                            elif message == '/sys talk':
                                self.new_message_signal.emit('sys_message', 'New partner, chat!')
                            else:
                                self.new_message_signal.emit('new_message', message)
                        else:
                            print('no data, partner disconnected?')
                            s.close()
                    except socket.error:
                        pass

        print('returning')

    def stop(self):
        #disconnettersi senza far crashare il server
        for c in self.inputs:
            c.close()
        self.sock.close()
        self.input = []
        self.running = False
        print('stopping thread...')

    def connect(self, address):
        self.new_message_signal.emit('sys_message', 'Connecting to '+ address+'...')
        self.client_address = address
        self.sock = socket.socket(AF_INET,SOCK_STREAM)
        self.sock.settimeout(3)

        try:
            #gestire l'eccezioni
            self.sock.connect((self.client_address, CHAT_PORT)) #se il server e' spento dovrebbe dare un eccezione non bloccarsi     
        except socket.error as ex:
            if ex.errno:
                print(os.strerror(ex.errno))
            if ex.errno == errno.EHOSTDOWN:
                self.new_message_signal.emit('sys_message', 'Server is down, try later')
            else:
                self.new_message_signal.emit('sys_message', "Can't connect, try later")
            return

        self.client_mode = True
        self.inputs.append(self.sock)
        self.new_message_signal.emit('sys_message', 'Connected to the server')
      
    def change_partner(self):
        self.send('/sys next','utf-8')

    def send(self, message):
        message = message.encode('utf-8')
        if self.connection or self.sock:
            if self.client_mode:
                self.sock.send(message) #controllare disconnessione
            else:
                self.connection.send(message)
        else:
            self.new_message_signal.emit('sys_message', "Can't send, are you connected? Try to restart the client")

class Video():
    def __init__(self, host, port):
        self.player = gst.Pipeline("player")
        tcpclientsrc = gst.element_factory_make("tcpclientsrc", "tcpclientsrc")
        tcpclientsrc.set_property("host", host)
        tcpclientsrc.set_property("port", port)
        #multipartdemux??
        colorspace = gst.element_factory_make("jpegdec")
        sink = gst.element_factory_make("autovideosink", "video-output")
        caps = gst.Caps("video/x-raw-yuv, width=320, height=240, framerate=20/1")
        self.player.add(tcpclientsrc, colorspace, sink)
        gst.element_link_many(tcpclientsrc, colorspace, sink)

        bus = self.player.get_bus()
        bus.add_signal_watch()
        bus.enable_sync_message_emission()
        #bus.connect("message", self.on_message)
        #bus.connect("sync-message::element", self.on_sync_message)

    def start(self):
        self.player.set_state(gst.STATE_PLAYING)

class Chat(gtk.Window):
    def __init__(self,new_message_signal, receiver):
        super(Chat, self).__init__()

        self.receiving = False

        self.set_default_size(480, 640)
        self.receiver = receiver
        self.connect("destroy", self.quit)
        
        self.vbox = gtk.VBox()
        #self.movie_window = gtk.DrawingArea()
        #vbox.pack_start(self.movie_window, expand=True, fill=True, padding=0)        
        self.add(self.vbox)
        self.view = gtk.TextView()
        self.view.set_editable(False)
        self.buffer = self.view.get_buffer()
        self.iter_pos = self.buffer.get_start_iter()
        scrolled_window=gtk.ScrolledWindow()
        scrolled_window.set_policy(gtk.POLICY_AUTOMATIC,gtk.POLICY_AUTOMATIC)
        scrolled_window.add(self.view)
        
        self.entry=gtk.Entry()
        self.send_button=gtk.Button("Send")
        self.send_button.connect("clicked", self.on_send_clicked)
        self.connect_button = gtk.Button("Connect")
        self.connect_button.connect("clicked", self.on_connect_clicked)
        self.next_button=gtk.Button("Next")
        self.next_button.connect("clicked", self.on_next_clicked)

        self.vbox.pack_start(self.next_button, expand=False, fill=False, padding=0)
        self.vbox.add(scrolled_window)

        self.hbox=gtk.HBox()
        self.hbox.pack_start(self.entry, expand=True, fill=True, padding=0)
        self.hbox.pack_start(self.send_button, expand=False, fill=False, padding=0)
        self.hbox.pack_start(self.connect_button, expand=False, fill=False, padding=0)
        self.vbox.pack_start(self.hbox, expand=False, fill=False, padding=0)
        self.show_all()

        self.entry.grab_focus()

        new_message_signal.connect('new_message', self.on_new_message)
        new_message_signal.connect('sys_message', self.on_sys_message)

        #self.video = Video()

        if self.receiving:
            self.video.start()

    def on_key_press_event(self, widget, event):
        keyname = gtk.gdk.keyval_name(event.keyval)
        #print "Key %s (%d) was pressed" % (keyname, event.keyval)
        if event.keyval == 65293:
            self.send_button.clicked()
        #if self.entry.has_focus:
        #    print('focus')
        #else:
        #    print('non focus')

    def quit(self, widget):
        self.receiver.stop()
        gtk.main_quit()

    def on_next_clicked(self, widget):
        self.receiver.send('/sys next')

    def on_send_clicked(self, widget):
        text = self.entry.get_text()
        if text == '':
            return
        self.receiver.send(text)
        self.buffer.insert(self.iter_pos,'You: '+text+'\n') #unificare
        self.entry.set_text('')

    def on_connect_clicked(self, widget):
        address = self.entry.get_text()
        self.receiver.connect(address)

    def on_new_message(self, widget, mess):
        self.buffer.insert(self.iter_pos, 'Partner: '+mess+'\n') #unificare

    def on_sys_message(self, widget, mess):
        self.buffer.insert(self.iter_pos, mess+'\n')
    
    def on_message(self, bus, message):
	    t = message.type
	    if t == gst.MESSAGE_EOS:
		    self.player.set_state(gst.STATE_NULL)
	    elif t == gst.MESSAGE_ERROR:
		    self.player.set_state(gst.STATE_NULL)
		    err, debug = message.parse_error()
		    print "Error: %s" % err, debug

    def on_sync_message(self, bus, message):
        if message.structure is None:
            return
        message_name = message.structure.get_name()
        if message_name == "prepare-xwindow-id":
            imagesink = message.src
            imagesink.set_property("force-aspect-ratio", True)
            gtk.gdk.threads_enter()
            imagesink.set_xwindow_id(self.movie_window.window.xid)
            gtk.gdk.threads_leave()

gobject.threads_init()

gobject.type_register(NewMessageSignal)
gobject.signal_new("new_message", NewMessageSignal, gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_STRING,))
gobject.signal_new("sys_message", NewMessageSignal, gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_STRING,))

new_message_signal = NewMessageSignal()
receiver = Receiver(new_message_signal)

c = Chat(new_message_signal, receiver)
c.connect('key_press_event', c.on_key_press_event)

receiver.start()
gtk.main()
