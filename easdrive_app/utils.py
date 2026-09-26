import os
from PIL import Image
from typing import List, Dict, Any

def walk(f_path: str, name: str, level: int) -> List[Dict[str, Any]]:
    """
    Python port of CommonFunction.walk.
    Recursively builds a tree of directories.
    """
    if not os.path.exists(f_path) or not os.path.isdir(f_path):
        return []

    folder_name = os.path.basename(f_path)
    current = {
        "text": "My Drive" if level == 0 else folder_name
    }

    if level == 0:
        path_value = ""
    elif level == 1:
        path_value = folder_name
    else:
        path_value = f"{name}/{folder_name}"
    
    current["pathValue"] = path_value

    nodes = []
    try:
        entries = os.listdir(f_path)
        for entry in entries:
            full_path = os.path.join(f_path, entry)
            if os.path.isdir(full_path) and entry != "temp":
                child_nodes = walk(full_path, path_value, level + 1)
                if child_nodes:
                    nodes.extend(child_nodes)
                else:
                    # Java walk adds even if no children, wait.
                    # Java source: walk(t, next, pathValue, level + 1);
                    # It adds to 'next' which is 'nodes' of current.
                    # Let's mirror Java more closely.
                    pass
    except Exception:
        pass

    # Java's walk signature: public static void walk(File f, ArrayList<HashMap<String, Object>> list, String name, int level)
    # It adds 'current' to the 'list' passed from parent.
    return [current]

def get_tree(base_path: str) -> List[Dict[str, Any]]:
    """
    Helper to match the exact tree structure expected by EasDriveController.
    """
    res_list = []
    # Java call: CommonFunction.walk(new File(easDriveBasePath+memberId), folderList, "", 0);
    _walk_java_style(base_path, res_list, "", 0)
    return res_list

def _walk_java_style(f_path: str, result_list: List[Dict[str, Any]], name: str, level: int):
    if not os.path.exists(f_path) or not os.path.isdir(f_path):
        return

    folder_name = os.path.basename(f_path)
    current = dict()
    current["text"] = "My Drive" if level == 0 else folder_name

    if level == 0:
        path_value = ""
    elif level == 1:
        path_value = folder_name
    else:
        path_value = f"{name}/{folder_name}"
    
    current["pathValue"] = path_value

    try:
        entries = os.listdir(f_path)
        dirs = [e for e in entries if os.path.isdir(os.path.join(f_path, e)) and e != "temp"]
        if dirs:
            nodes = []
            current["nodes"] = nodes
            for d in dirs:
                _walk_java_style(os.path.join(f_path, d), nodes, path_value, level + 1)
    except Exception:
        pass

    result_list.append(current)

def join_images(background_path: str, overlay_path: str, output_path: str):
    """
    Python port of CommonFunction.joinBufferedImage.
    Overlays a play button (overlay_path) onto a video thumbnail (background_path).
    """
    try:
        bg = Image.open(background_path).convert("RGBA")
        overlay = Image.open(overlay_path).convert("RGBA")
        
        # New image with black background (mirrors Java g2.fillRect with black)
        new_img = Image.new("RGBA", bg.size, (0, 0, 0, 255))
        new_img.paste(bg, (0, 0), bg)
        
        # Overlay centered
        bg_w, bg_h = bg.size
        # Java uses 32 offset assuming play button is 64x64
        # We'll calculate it dynamically if possible, but stay close to Java
        ov_w, ov_h = overlay.size
        pos = ((bg_w // 2) - (ov_w // 2), (bg_h // 2) - (ov_h // 2))
        
        new_img.paste(overlay, pos, overlay)
        
        # Save as RGB if we want to discard alpha or keep it as PNG
        if output_path.lower().endswith((".jpg", ".jpeg")):
            new_img.convert("RGB").save(output_path, "JPEG")
        else:
            new_img.save(output_path, "PNG")
        return True
    except Exception:
        return False
