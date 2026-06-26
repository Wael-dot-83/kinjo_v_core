import re

path = r'D:\Final Version\static\js\jordan_cesium_map.js'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the image: createPinSvg(hexClr, isCrit) with the real image logic.
# Also apply color tint so risk is still visible, and dynamically set image.
old_image = r"image: createPinSvg(hexClr, isCrit),"
new_image = r"""image: '/static/img/real_school_pin.png',
        color: pinColor, // Tint the real image with the risk color"""

content = content.replace(old_image, new_image)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Real pin image modification applied.")
