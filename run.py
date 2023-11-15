#! /usr/bin/env python
from app import socketio,app


if __name__ == "__main__":
    #app.run(debug=True)
    #app.run(debug=True,host='192.168.1.91')
    #socketio.run(app, host='192.168.1.91', port=5000)
    socketio.run(app, debug=True)
