# Preview of generic digital faces

import time
import os
import gc
import json
import errno
import struct
import sys
import uasyncio
import lvgl as lv

from micropython import const

_USAGE = """
Before preview set MicroPython executable as $mp environment variable:
    mp=~/src/lv_micropython/ports/unix/micropython-dev

Usage:
    $mp preview.py
    $mp preview.py [face name] 
    $mp preview.py [face name] [snapshot file] [time tuple]
    $mp preview.py --help
    $mp preview.py --snapshot-for-all [snapshot name postfix] [snapshots path] [time tuple] 

    [face name]                 Preview given face. (Optional)
    [snapshot file]             Take snapshot of face preview and save as RAW file. (Optional)
    [time tuple]                Show given time instead of actaul time. Tuple: (YYYY, MM, DD, HH, mm, ss, weekday) (Optional)

    --help                      Show current usage help

    --snapshot-for-all          Take snapshot RAW files for all faces
    [snapshot name postfix]     Snapshot file postfix (example: "_preview.raw") (Required)
    [snapshots path]            Path to store snapshot RAW files (example: _previews) (Required)
    [time tuple]                Show given time instead of actaul time. Tuple: (YYYY, MM, DD, HH, mm, ss, weekday) (Required)

Snapshot files are generated as BGRA RAW images.
They can be converted to PNG/JPEG/WebP image format with the script: "[repo]/tools/convert_snapshot_to_image.py"
"""

_FACE_FILE = "face.json"
_WIDTH = const(240)
_HEIGHT = const(240)
_MARGIN_PERCENT = const(20)
_DRIVE_LETTER = const('S')
_FS_CACHE_SIZE = const(2048)
_IMG_CACHE_COUNT = const(32)

_TYPE_DIRECTORY = const(0x4000)

_MENU_ITEM_WIDTH = const(200)
_MENU_ITEM_HEIGHT = const(50)


# ************************************
# Face implementation
# ************************************
_FONTS_PATH = _DRIVE_LETTER + ":fonts/"

_WEEK_DAYS = ["Monday", "Tuesday", "Wednesday",
              "Thursday", "Friday", "Saturday", "Sunday"]
_WEEK_DAYS_SHORT = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]

_MONTHS = ["January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"]
_MONTHS_SHORT = ["JAN", "FEB", "MAR", "APR", "MAY",
                 "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

_PLACEHOLDERS = {
    "{YYYY}": lambda context: f"{context.year:04d}",
    "{MM}": lambda context: f"{context.month:02d}",
    "{DD}": lambda context: f"{context.day:02d}",
    "{HH}": lambda context: f"{context.hour:02d}",
    "{mm}": lambda context: f"{context.minute:02d}",
    "{ss}": lambda context: f"{context.second:02d}",
    "{day}": lambda context: _WEEK_DAYS[context.weekday],
    "{day_short}": lambda context: _WEEK_DAYS_SHORT[context.weekday],
    "{month}": lambda context: _MONTHS[context.month - 1],
    "{month_short}": lambda context: _MONTHS_SHORT[context.month - 1],
    "{battery_percent}": lambda context: "100"
}

_HANDLE_SOURCE_DEFAULT_VALUES = {
    "hour": (0, 12, 0, 360),
    "minute": (0, 60, 0, 360),
    "second": (0, 60, 0, 360)
}

_HANDLE_SOURCE_GET_VALUES = {
    "hour": lambda context: (context.hour % 12) + (context.minute / 60),
    "minute": lambda context: context.minute,
    "second": lambda context: context.second,
}

# Shortcuts to improve lookup performance
__LV_ALIGN = lv.ALIGN
__LV_TEXT_ALIGN = lv.TEXT_ALIGN
__LV_LABEL = lv.label
__ALIGN_CENTER = lv.ALIGN.CENTER


class Context:
    year: int = None
    month: int = None
    day: int = None
    hour: int = None
    minute: int = None
    second: int = None
    weekday: int = None
    yearday: int = None
    get_info: function = None

    def __init__(self, get_info: function = None):
        self.get_info = get_info or (lambda _: "")

    def set_time(self, time_tuple):
        self.year, self.month, self.day, self.hour, self.minute, self.second, self.weekday, self.yearday = time_tuple[
            0:8]


class Renderer:
    def __init__(self, screen):
        self._screen = screen

        self._container: lv.obj = None
        self._fonts = {}
        self._labels = []
        self._handles = []
        self._images = []
        self._gifs = []
        self._gif_data = []

        self._item_load_function = {
            "label": self._load_label,
            "image": self._load_image,
            "gif": self._load_gif,
            "handle": self._load_handle
        }

    def load(self, path, config):
        container = lv.obj(self._screen)
        container.remove_style_all()
        container.set_size(lv.pct(100), lv.pct(100))
        container.add_flag(lv.obj.FLAG.EVENT_BUBBLE)
        container.add_flag(lv.obj.FLAG.GESTURE_BUBBLE)

        if config["version"] != "1":
            raise Exception("Not supported version: " + config["version"])

        # Set background color and image
        item = config.get("background", None)
        if item:
            if "color" in item:
                color = self._hex_color(item.get("color", "#000"))
                container.set_style_bg_color(color, 0)
                container.set_style_bg_opa(lv.OPA.COVER, 0)

            if "image" in item:
                image_path = f"{path}/{item.get('image')}"
                try:
                    image = self._show_image(
                        container, image_path, __ALIGN_CENTER, 0, 0)
                    self._images.append(image)
                    container = image
                except:
                    raise Exception(f"Image not found: {image_path}")

        # Calculate container position and size, so items can calculate their own (absolute) positions inside container
        container.refr_pos()
        container.refr_size()
        self._container = container

        # Load items one-by-one (order is important, as it defines drawing Z-index)
        for item in config.get("items", []):
            item_type = item.get("type", None)
            if not item_type:
                continue

            load_function = self._item_load_function.get(item_type, None)
            if load_function:
                load_function(container, item, path)

    def unload(self):
        for x in self._images:
            del x

        for x in self._handles:
            del x

        for x in self._gifs:
            del x

        for x in self._gif_data:
            del x

        for x in self._fonts.values():
            x.free()
            del x

        self._images.clear()
        self._handles.clear()
        self._gifs.clear()
        self._gif_data.clear()
        self._labels.clear()
        self._fonts.clear()

    def show(self, context: Context):
        # Update labels
        for label in self._labels:
            text: str = label["text"]

            for key, transform_cb in _PLACEHOLDERS.items():
                if key in text:
                    text = text.replace(key, transform_cb(context))

            if text != label["value"]:
                label["value"] = text
                label["lv_label"].set_text(text)

        # Rotate handles
        for handle in self._handles:
            value = _HANDLE_SOURCE_GET_VALUES.get(
                handle["source"], lambda _: 0)(context)
            (min_value, max_value, min_angle, max_angle) = handle["ranges"]

            angle = int(
                (min_angle + ((min_value + value) / max_value) * max_angle) * 10)
            handle["image"].set_angle(angle)

    def _load_label(self, parent: lv.obj, item: dict, path: str):
        text = item.get("text", "")
        color = self._hex_color(item.get("color", "#000"))

        x = item.get("x", 0)
        y = item.get("y", 0)

        align = __LV_ALIGN.__dict__.get(
            item.get("align", None), __LV_ALIGN.TOP_LEFT)
        textalign = __LV_TEXT_ALIGN.__dict__.get(
            item.get("textalign", None), __LV_TEXT_ALIGN.LEFT)

        label = __LV_LABEL(parent)
        label.set_style_text_color(color, 0)
        label.set_style_text_align(textalign, 0)
        label.set_recolor(True)
        label.align(align, x, y)
        label.set_text("")

        font_name = item.get("font", None)
        if font_name:
            font_path = _FONTS_PATH + font_name
            font = self._fonts.get(font_name, None)
            if not font:
                font = lv.font_load(font_path)
                self._fonts[font_name] = font
            label.set_style_text_font(font, 0)

        self._labels.append({
            "lv_label": label,
            "text": text,
            "value": ""
        })

    def _load_image(self, parent: lv.obj, item: dict, path: str):
        filename = item.get("file")
        x = item.get("x", 0)
        y = item.get("y", 0)
        align = __LV_ALIGN.__dict__.get(
            item.get("align", None), __LV_ALIGN.TOP_LEFT)

        img = self._show_image(parent, f"{path}/{filename}", align, x, y)
        self._images.append(img)

    def _load_gif(self, parent: lv.obj, item: dict, path: str):
        filename = item.get("file")
        x = item.get("x", 0)
        y = item.get("y", 0)
        align = __LV_ALIGN.__dict__.get(
            item.get("align", None), __LV_ALIGN.TOP_LEFT)

        img_dsc = self._get_lv_img_dsc(f"{path}/{filename}")
        self._gif_data.append(img_dsc)

        gif = lv.gif(parent)
        gif.align(align, x, y)
        gif.set_src(img_dsc)
        self._gifs.append(gif)

    def _load_handle(self, parent: lv.obj, item: dict, path: str):
        filename = item.get("image")
        x = item.get("x", 0)
        y = item.get("y", 0)
        pivot_x = item.get("pivot_x", 0)
        pivot_y = item.get("pivot_y", 0)
        align = __LV_ALIGN.__dict__.get(
            item.get("align", None), __LV_ALIGN.TOP_LEFT)

        source = item.get("source", None)
        source_default_values = _HANDLE_SOURCE_DEFAULT_VALUES.get(
            source, (0, 100, 0, 360))
        ranges = (item.get("min_value", source_default_values[0]),
                  item.get("max_value", source_default_values[1]),
                  item.get("min_angle", source_default_values[2]),
                  item.get("max_angle", source_default_values[3]))

        img = self._show_image(parent, f"{path}/{filename}", align, x, y)

        # Fix image alignment with pivot point
        if align != __LV_ALIGN.TOP_LEFT:
            img.refr_size()
            img.refr_pos()
            x, y, w, h = img.get_x(), img.get_y(), img.get_width(), img.get_height()
            img.align(__LV_ALIGN.TOP_LEFT, x - w // 2 +
                      (w - pivot_x), y - h // 2 + (h - pivot_y))

        img.set_pivot(pivot_x, pivot_y)

        self._handles.append({
            "image": img,
            "source": source,
            "ranges": ranges
        })

    def _hex_color(self, value):
        color_int = int(value.lstrip("#"), 16)
        return lv.color_hex(color_int)

    def _show_image(self, parent, path, align=lv.ALIGN.CENTER, x=0, y=0):
        image_desc = self._get_lv_img_dsc(path)
        image = lv.img(parent)
        image.align(align, x, y)
        image.set_src(image_desc)
        image.refr_pos()
        image.refr_size()
        return image

    def _get_lv_img_dsc(self, filepath):
        with open(filepath, "rb") as f:
            image_data = f.read()

        return lv.img_dsc_t({
            "data": image_data,
            "data_size": len(image_data)
        })


# ************************************
# LVGL FS Driver
# ************************************
_RET_OK = lv.FS_RES.OK
_RET_FS_ERR = lv.FS_RES.FS_ERR


class LVGL_FS_File:
    def __init__(self, file, path):
        self.file = file
        self.path = path


class LVGL_FS_Driver():
    def __init__(self, base_path, fs_drv, letter, cache_size):
        self._base_path = base_path

        fs_drv.init()
        fs_drv.letter = ord(letter)
        fs_drv.cache_size = cache_size
        fs_drv.open_cb = self.open_cb
        fs_drv.read_cb = self.read_cb
        fs_drv.write_cb = self.write_cb
        fs_drv.seek_cb = self.seek_cb
        fs_drv.tell_cb = self.tell_cb
        fs_drv.close_cb = self.close_cb
        fs_drv.register()

    def open_cb(self, drv, path, mode):
        if mode == lv.FS_MODE.WR:
            p_mode = 'wb'
        elif mode == lv.FS_MODE.RD:
            p_mode = 'rb'
        elif mode == lv.FS_MODE.WR | lv.FS_MODE.RD:
            p_mode = 'rb+'
        else:
            raise RuntimeError(
                f"open_cb('{path}', {mode}) - open mode error, '{mode}' is invalid mode")

        try:
            f = open(f"{self._base_path}/{path}", p_mode)
        except Exception as e:
            raise RuntimeError(
                f"open_cb('{path}', '{p_mode}') error: ", errno.errorcode[e.args[0]])

        return LVGL_FS_File(f, path)

    def close_cb(self, drv, fs_file):
        try:
            fs_file.__cast__().file.close()
        except Exception as e:
            print(
                f"close_cb('{fs_file.__cast__().path}') error: {errno.errorcode[e.args[0]]}", e)
            return _RET_FS_ERR

        return _RET_OK

    def read_cb(self, drv, fs_file, buf, btr, br):
        try:
            tmp_data = buf.__dereference__(btr)
            bytes_read = fs_file.__cast__().file.readinto(tmp_data)
            br.__dereference__(4)[0:4] = struct.pack("<L", bytes_read)
        except Exception as e:
            print(
                f"read_cb('{fs_file.__cast__().path}', {btr}) error: {errno.errorcode[e.args[0]]}", e)
            return _RET_FS_ERR

        return _RET_OK

    def seek_cb(self, drv, fs_file, pos, whence):
        try:
            fs_file.__cast__().file.seek(pos, whence)
        except Exception as e:
            print(
                f"seek_cb('{fs_file.__cast__().path}', {pos}, {whence}) error: {errno.errorcode[e.args[0]]}", e)
            return _RET_FS_ERR

        return _RET_OK

    def tell_cb(self, drv, fs_file, pos):
        try:
            tpos = fs_file.__cast__().file.tell()
            pos.__dereference__(4)[0:4] = struct.pack("<L", tpos)
        except Exception as e:
            print(
                f"tell_cb('{fs_file.__cast__().path}') error: {errno.errorcode[e.args[0]]}", e)
            return _RET_FS_ERR

        return _RET_OK

    def write_cb(self, drv, fs_file, buf, btw, bw):
        try:
            wr = fs_file.__cast__().file.write(buf[0:btw])
            bw.__dereference__(4)[0:4] = struct.pack("<L", wr)
        except Exception as e:
            print(
                f"write_cb('{fs_file.__cast__().path}', {btw}) error: {errno.errorcode[e.args[0]]}", e)
            return _RET_FS_ERR

        return _RET_OK

# ************************************
# Main app
# ************************************


class App():
    def __init__(self):
        self._faces_path = os.getcwd()
        self._root_path = self._faces_path.rsplit("/", 2)[0]
        self._faces = []
        self._face_screen: lv.obj = None
        self._menu_screen: lv.obj = None
        self._context: Context = None
        self._renderer: Renderer = None
        self._face_selector_dropdown: lv.dropdown = None
        self._is_running = False

        self._load_faces_list()
        self._init_lvgl()
        self._init_lvgl_fs()
        self._init_lvgl_image_decoders()
        self._init_menu_screen()
        self._init_face_screen()
        self._init_renderer()

    async def loop(self, face_name=None):
        if face_name and face_name in self._faces and self._path_exists(f"{self._faces_path}/{face_name}"):
            self._face_selector_dropdown.set_selected(
                self._faces.index(face_name))
            self._show_face(face_name)
        else:
            self._show_menu()

        self._is_running = True
        while self._is_running:
            self._context.set_time(time.localtime())
            self._renderer.show(self._context)
            await uasyncio.sleep_ms(250)

    def snapshot_all(self, snapshot_name_postfix, snapshots_path, time_tuple):
        for face_name in self._faces:
            snapshot_file_name = f"{snapshots_path}/{face_name}{snapshot_name_postfix}"
            self.snapshot(face_name, snapshot_file_name, time_tuple)
            lv.img.cache_invalidate_src(None)
            gc.collect()

    def snapshot(self, face_name, snapshot_file_name, time_tuple):
        if not face_name or not self._path_exists(f"{self._faces_path}/{face_name}"):
            print(f"Face does not exist: {face_name}")
            return

        self._face_screen.clean()
        self._show_face(face_name, time_tuple)
        snapshot = lv.snapshot_take(
            self._face_screen, lv.COLOR_FORMAT.ARGB8888)
        size = self._face_screen.get_width() * self._face_screen.get_height() * 4
        data = snapshot.data.__dereference__(size)
        with open(snapshot_file_name, "wb") as f:
            f.write(data)

        lv.snapshot_free(snapshot)
        self._renderer.unload()
        print(f"Snapshot file: {snapshot_file_name} ({size} bytes)")

    def _init_lvgl(self):
        lv.init()

        # Init display
        display = lv.sdl_window_create(_WIDTH, _HEIGHT)

        # Init mouse
        mouse = lv.sdl_mouse_create()
        mouse.set_disp(display)

        import lv_utils
        lv_utils.event_loop(asynchronous=True)

    def _init_lvgl_fs(self):
        lv_fs_drv = lv.fs_drv_t()
        LVGL_FS_Driver(self._root_path, lv_fs_drv,
                       _DRIVE_LETTER, _FS_CACHE_SIZE)

    def _init_lvgl_image_decoders(self):
        lv.img.cache_set_size(_IMG_CACHE_COUNT)
        lv.split_jpeg_init()

    def _create_screen(self):
        screen = lv.obj()
        screen.remove_style_all()
        screen.set_style_bg_color(lv.color_black(), 0)
        screen.set_style_bg_opa(lv.OPA.COVER, 0)
        screen.set_style_text_color(lv.color_white(), 0)
        return screen

    def _init_menu_screen(self):
        self._menu_screen = self._create_screen()
        screen = self._menu_screen
        screen.set_size(lv.pct(100), lv.pct(100))
        screen.set_style_pad_ver(10, 0)
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        screen.set_flex_align(lv.FLEX_ALIGN.START,
                              lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        screen.set_style_pad_row(10, lv.STATE.DEFAULT)

        # Faces dropdown
        dd = lv.dropdown(screen)
        dd.set_width(_MENU_ITEM_WIDTH)
        dd.set_options("\n".join(self._faces))
        self._face_selector_dropdown = dd

        # Show button
        button = lv.btn(screen)
        button.set_size(_MENU_ITEM_WIDTH, _MENU_ITEM_HEIGHT)
        button.add_event(self._show_button_cb, lv.EVENT.CLICKED, None)
        label = lv.label(button)
        label.set_text("Show")
        label.center()

        # Reload list button
        button = lv.btn(screen)
        button.set_size(_MENU_ITEM_WIDTH, _MENU_ITEM_HEIGHT)
        button.set_style_bg_color(lv.color_hex(0x00CC00), 0)
        button.add_event(self._reload_button_cb, lv.EVENT.CLICKED, None)
        label = lv.label(button)
        label.set_text("Reload list")
        label.center()

        # Exit button
        button = lv.btn(screen)
        button.set_size(_MENU_ITEM_WIDTH, _MENU_ITEM_HEIGHT)
        button.set_style_bg_color(lv.color_hex(0xFF0000), 0)
        button.add_event(self._exit_button_cb, lv.EVENT.CLICKED, None)
        label = lv.label(button)
        label.set_text("Exit")
        label.center()

    def _init_face_screen(self):
        self._face_screen = self._create_screen()
        self._face_screen.add_event(
            self._face_screen_click_cb, lv.EVENT.CLICKED, None)

    def _init_renderer(self):
        self._context = Context()
        self._renderer = Renderer(self._face_screen)

    def _load_faces_list(self):
        faces = [entry[0] for entry in os.ilistdir(
            self._faces_path) if entry[1] == _TYPE_DIRECTORY and not entry[0].startswith("_")]
        faces.sort()
        self._faces = faces

    def _show_button_cb(self, event):
        face_name = self._faces[self._face_selector_dropdown.get_selected()]
        self._show_face(face_name)

    def _reload_button_cb(self, event):
        current_face_name = self._faces[self._face_selector_dropdown.get_selected(
        )]
        self._load_faces_list()
        self._face_selector_dropdown.set_options("\n".join(self._faces))
        if current_face_name in self._faces:
            self._face_selector_dropdown.set_selected(
                self._faces.index(current_face_name))

    def _exit_button_cb(self, event):
        self._is_running = False

    def _show_menu(self):
        lv.scr_load(self._menu_screen)

    def _show_face(self, name, time_tuple=None):
        lv.scr_load(self._face_screen)

        face_path = f"{self._faces_path}/{name}"
        with open(f"{face_path}/{_FACE_FILE}", "r") as f:
            config = json.load(f)

        print("Show face: ", face_path)
        self._context.set_time(time_tuple or time.localtime())
        self._renderer.load(face_path, config)
        self._renderer.show(self._context)

    def _face_screen_click_cb(self, event):
        if self._renderer:
            self._renderer.unload()
            lv.img.cache_invalidate_src(None)
            gc.collect()

        # If left or right side is touched, then show previous/next face
        show_other_face = False
        w = self._face_screen.get_width()
        m = int(w * _MARGIN_PERCENT / 100)
        p = lv.point_t()
        event.get_indev().get_point(p)
        index = self._face_selector_dropdown.get_selected()
        if p.x < m:
            index = max(0, index - 1)
            show_other_face = True
        elif p.x > w - m:
            index = min(len(self._faces) - 1, index + 1)
            show_other_face = True

        if show_other_face:
            self._face_selector_dropdown.set_selected(index)
            self._show_face(self._faces[index])
        else:
            self._show_menu()

    def _path_exists(self, path):
        try:
            stat = os.stat(path)
            return stat[0] & _TYPE_DIRECTORY > 0
        except:
            return False


# ************************************
# Program entry point
# ************************************

app = App()


def get_time_tuple(arg):
    return tuple(map(lambda x: int(x), arg.strip("()").replace(" ", "").split(",")))


arg1 = sys.argv[1] if len(sys.argv) > 1 else None

# No argument: show preview screen
if arg1 == None:
    # uasyncio.run(app.loop())
    # event_loop.create_task(app.loop())
    uasyncio.run(app.loop())
    sys.exit()

# Show help
if arg1 == "--help":
    print(_USAGE)
    sys.exit()

# Take snapshot of all faces
if arg1 == "--snapshot-for-all":
    try:
        snapshot_name_postfix = sys.argv[2]
        snapshots_path = sys.argv[3]
        time_tuple = get_time_tuple(sys.argv[4]) if len(sys.argv) > 3 else None
    except:
        print(_USAGE)
        sys.exit(1)

    app.snapshot_all(snapshot_name_postfix, snapshots_path, time_tuple)
    sys.exit(0)

# Show or take snapshot of a given face
face_name = arg1
snapshot_file_name = sys.argv[2] if len(sys.argv) > 2 else None
time_tuple = get_time_tuple(sys.argv[3]) if len(sys.argv) > 3 else None
if snapshot_file_name:
    app.snapshot(face_name, snapshot_file_name, time_tuple)
else:
    uasyncio.run(app.loop(face_name))
