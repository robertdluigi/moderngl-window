from PyQt5 import QtCore, QtOpenGL, QtWidgets

from moderngl_window.context.base import BaseWindow
from moderngl_window.context.pyqt5.keys import Keys


class Window(BaseWindow):
    """
    A basic window implementation using PyQt5 with the goal of
    creating an OpenGL context and handle keyboard and mouse input.

    This window bypasses Qt's own event loop to make things as flexible as possible.

    If you need to use the event loop and are using other features
    in Qt as well, this example can still be useful as a reference
    when creating your own window.
    """
    #: PyQt5 specific key constants
    keys = Keys

    # PyQt supports mode buttons, but we are limited by other libraries
    _mouse_button_map = {
        1: 1,
        2: 2,
        4: 3,
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Specify OpenGL context parameters
        gl = QtOpenGL.QGLFormat()
        gl.setVersion(self.gl_version[0], self.gl_version[1])
        gl.setProfile(QtOpenGL.QGLFormat.CoreProfile)
        gl.setDepthBufferSize(24)
        gl.setDoubleBuffer(True)
        gl.setSwapInterval(1 if self.vsync else 0)

        # Configure multisampling if needed
        if self.samples > 1:
            gl.setSampleBuffers(True)
            gl.setSamples(self.samples)

        # We need an application object, but we are bypassing the library's
        # internal event loop to avoid unnecessary work
        self.app = QtWidgets.QApplication([])

        # Create the OpenGL widget
        self.widget = QtOpenGL.QGLWidget(gl)
        self.widget.setWindowTitle(self.title)

        # If fullscreen we change the window to match the desktop on the primary screen
        if self.fullscreen:
            rect = QtWidgets.QDesktopWidget().screenGeometry()
            self._width = rect.width()
            self._height = rect.height()
            self._buffer_width = rect.width() * self.widget.devicePixelRatio()
            self._buffer_height = rect.height() * self.widget.devicePixelRatio()

        if self.resizable:
            # Ensure a valid resize policy when window is resizable
            size_policy = QtWidgets.QSizePolicy(
                QtWidgets.QSizePolicy.Expanding,
                QtWidgets.QSizePolicy.Expanding,
            )
            self.widget.setSizePolicy(size_policy)
            self.widget.resize(self.width, self.height)
        else:
            self.widget.setFixedSize(self.width, self.height)

        # Center the window on the screen if in window mode
        if not self.fullscreen:
            self.widget.move(QtWidgets.QDesktopWidget().rect().center() - self.widget.rect().center())

        # Needs to be set before show()
        self.widget.resizeGL = self.resize

        if not self.cursor:
            self.widget.setCursor(QtCore.Qt.BlankCursor)

        if self.fullscreen:
            self.widget.showFullScreen()
        else:
            self.widget.show()

        # We want mouse position events
        self.widget.setMouseTracking(True)

        # Override event functions in qt
        self.widget.keyPressEvent = self.key_pressed_event
        self.widget.keyReleaseEvent = self.key_release_event
        self.widget.mouseMoveEvent = self.mouse_move_event
        self.widget.mousePressEvent = self.mouse_press_event
        self.widget.mouseReleaseEvent = self.mouse_release_event
        self.widget.wheelEvent = self.mouse_wheel_event
        self.widget.closeEvent = self.close_event

        # Attach to the context
        self.init_mgl_context()

        # Ensure retina and 4k displays get the right viewport
        self._buffer_width = self._width * self.widget.devicePixelRatio()
        self._buffer_height = self._height * self.widget.devicePixelRatio()

        self.set_default_viewport()

    def swap_buffers(self) -> None:
        """Swap buffers, set viewport, trigger events and increment frame counter"""
        self.widget.swapBuffers()
        self.set_default_viewport()
        self.app.processEvents()
        self._frames += 1

    def resize(self, width: int, height: int) -> None:
        """Replacement for Qt's ``resizeGL`` method.

        Args:
            width: New window width
            height: New window height
        """
        self._width = width // self.widget.devicePixelRatio()
        self._height = height // self.widget.devicePixelRatio()
        self._buffer_width = width
        self._buffer_height = height

        if self._ctx:
            self.set_default_viewport()

        # Make sure we notify the example about the resize
        super().resize(self._buffer_width, self._buffer_height)

    def _handle_modifiers(self, mods) -> None:
        """Update modifiers"""
        self._modifiers.shift = mods & QtCore.Qt.ShiftModifier
        self._modifiers.ctrl = mods & QtCore.Qt.ControlModifier

    def key_pressed_event(self, event) -> None:
        """Process Qt key press events forwarding them to standard methods

        Args:
            event: The qtevent instance
        """
        if event.key() == self.keys.ESCAPE:
            self.close()

        self._handle_modifiers(event.modifiers())
        self._key_pressed_map[event.key()] = True
        self.key_event_func(event.key(), self.keys.ACTION_PRESS, self._modifiers)

    def key_release_event(self, event) -> None:
        """Process Qt key release events forwarding them to standard methods

        Args:
            event: The qtevent instance
        """
        self._handle_modifiers(event.modifiers())
        self._key_pressed_map[event.key()] = False
        self.key_event_func(event.key(), self.keys.ACTION_RELEASE, self._modifiers)

    def mouse_move_event(self, event) -> None:
        """Forward mouse cursor position events to standard methods

        Args:
            event: The qtevent instance
        """
        self.mouse_position_event_func(event.x(), event.y())

    def mouse_press_event(self, event) -> None:
        """Forward mouse press events to standard methods

        Args:
            event: The qtevent instance
        """
        button = self._mouse_button_map.get(event.button())
        if button is None:
            return

        self._handle_mouse_button_state_change(button, True)
        self.mouse_press_event_func(event.x(), event.y(), button)

    def mouse_release_event(self, event) -> None:
        """Forward mouse release events to standard methods

        Args:
            event: The qtevent instance
        """
        button = self._mouse_button_map.get(event.button())
        if button is None:
            return

        self._handle_mouse_button_state_change(button, False)
        self.mouse_release_event_func(event.x(), event.y(), button)

    def mouse_wheel_event(self, event):
        """Forward mouse wheel events to standard metods.

        From Qt docs:

        Returns the distance that the wheel is rotated, in eighths of a degree.
        A positive value indicates that the wheel was rotated forwards away from the user;
        a negative value indicates that the wheel was rotated backwards toward the user.

        Most mouse types work in steps of 15 degrees, in which case the delta value is a
        multiple of 120; i.e., 120 units * 1/8 = 15 degrees.

        However, some mice have finer-resolution wheels and send delta values that are less
        than 120 units (less than 15 degrees). To support this possibility, you can either
        cumulatively add the delta values from events until the value of 120 is reached,
        then scroll the widget, or you can partially scroll the widget in response to each
        wheel event.

        Args:
            event (QWheelEvent): Mouse wheel event
        """
        point = event.angleDelta()
        self._mouse_scroll_event_func(point.x() / 120.0, point.y() / 120.0)

    def close_event(self, event) -> None:
        """The standard PyQt close events

        Args:
            event: The qtevent instance
        """
        self.close()

    def destroy(self) -> None:
        """Quit the Qt application to exit the window gracefully"""
        QtCore.QCoreApplication.instance().quit()
