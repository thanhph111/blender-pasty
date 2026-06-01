import bpy


def image_from_node(node: object) -> bpy.types.Image | None:
    if getattr(node, "bl_idname", None) != "ShaderNodeTexImage":
        return None

    image = getattr(node, "image", None)
    if isinstance(image, bpy.types.Image):
        return image
    return None


def image_from_material(material: bpy.types.Material | None) -> bpy.types.Image | None:
    # Do not read material.use_nodes here. Blender 5.1 warns that it is going away in 6.0.
    # In newer Blender, material.node_tree is the useful check.
    if material is None or material.node_tree is None:
        return None

    nodes = material.node_tree.nodes
    active_image = image_from_node(nodes.active)
    if active_image is not None:
        return active_image

    for node in nodes:
        image = image_from_node(node)
        if image is not None:
            return image

    return None


def image_from_object(obj: bpy.types.Object | None) -> bpy.types.Image | None:
    if obj is None:
        return None

    if obj.type == "EMPTY" and obj.empty_display_type == "IMAGE":
        # Image reference objects store their image directly on object.data.
        if isinstance(obj.data, bpy.types.Image):
            return obj.data
        return None

    # Mesh objects do not own images directly; look through their active material.
    return image_from_material(obj.active_material)
