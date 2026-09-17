#!/usr/bin/env python3
"""
Generate a beautiful SVG map of North America for Conductor.
Uses simplified coastline paths for US, Canada, and Mexico.
"""

def generate_map():
    """Generate SVG map with realistic North American geography."""
    
    # SVG viewBox coordinates: 0 0 1024 683
    svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 683" width="1024" height="683">
  <!-- Ocean background (nice blue) -->
  <rect width="1024" height="683" fill="#1a3a52"/>
  
  <!-- Great Lakes (darker water) -->
  <g fill="#1a3a52" opacity="1">
    <!-- Lake Superior -->
    <ellipse cx="580" cy="135" rx="50" ry="38"/>
    <!-- Lake Michigan -->
    <ellipse cx="610" cy="185" rx="22" ry="32"/>
    <!-- Lake Huron -->
    <ellipse cx="650" cy="150" rx="28" ry="40"/>
    <!-- Lake Erie -->
    <ellipse cx="670" cy="225" rx="35" ry="18"/>
    <!-- Lake Ontario -->
    <ellipse cx="730" cy="195" rx="25" ry="22"/>
  </g>
  
  <!-- Canada - simplified but recognizable shape -->
  <path d="M 50 85 Q 100 70 150 65 Q 200 60 250 62 Q 300 58 350 60 Q 400 55 450 58 Q 500 55 550 62 Q 600 60 650 65 Q 700 62 750 68 Q 800 72 850 78 Q 900 82 950 95 Q 980 110 990 140 L 985 180 Q 975 200 950 210 Q 920 215 880 210 Q 850 215 820 212 Q 790 218 760 215 Q 730 220 700 218 Q 670 222 640 220 Q 610 225 580 220 Q 550 225 520 222 Q 490 226 460 223 Q 430 227 400 224 Q 370 228 340 225 Q 310 229 280 226 Q 250 230 220 227 Q 190 231 160 228 Q 130 232 100 229 Q 80 220 70 200 Q 60 170 62 140 Q 65 110 55 90 Z" 
        fill="#d9c4a8" stroke="#8b7355" stroke-width="2"/>
  
  <!-- United States - more organic shape -->
  <path d="M 70 220 Q 100 215 130 218 Q 160 215 190 220 Q 220 218 250 222 Q 280 220 310 225 Q 340 223 370 228 Q 400 225 430 230 Q 460 228 490 233 Q 520 230 550 235 Q 580 233 610 238 Q 640 235 670 240 Q 700 238 730 243 Q 760 240 790 245 Q 820 243 850 248 Q 880 245 910 250 Q 940 253 970 265 L 975 300 Q 978 340 975 380 Q 972 420 960 460 Q 940 520 900 560 Q 860 590 800 610 Q 750 630 680 645 Q 620 658 550 665 Q 480 670 410 668 Q 340 665 280 660 Q 220 655 160 650 Q 110 645 75 630 Q 50 610 45 560 Q 42 510 45 460 Q 48 410 50 360 Q 52 310 55 260 Q 58 240 70 220 Z" 
        fill="#e8d4b8" stroke="#8b7355" stroke-width="2"/>
  
  <!-- Mexico - simplified shape -->
  <path d="M 280 625 Q 320 620 360 625 Q 400 622 440 628 Q 480 625 520 632 Q 545 635 560 655 Q 540 675 500 680 Q 460 682 420 680 Q 380 682 340 680 Q 300 682 260 678 Q 240 670 250 645 Q 265 630 280 625 Z" 
        fill="#d9c4a8" stroke="#8b7355" stroke-width="2"/>
  
  <!-- Rivers (very subtle) -->
  <g stroke="#2a5280" stroke-width="0.8" opacity="0.25" fill="none" stroke-linecap="round">
    <!-- Mississippi River approximation -->
    <path d="M 480 230 Q 500 280 510 350 Q 515 420 520 500"/>
    <!-- Colorado River approximation -->
    <path d="M 240 350 Q 220 420 215 550"/>
    <!-- Rio Grande -->
    <path d="M 380 630 Q 400 640 420 655"/>
  </g>
  
  <!-- Subtle coastline details with curves -->
  <g stroke="#a89878" stroke-width="0.5" opacity="0.15" fill="none">
    <!-- Pacific Coast detail -->
    <path d="M 75 300 Q 70 350 72 400 Q 75 450 82 500"/>
    <!-- Atlantic Coast detail -->
    <path d="M 975 300 Q 980 350 978 400 Q 975 450 968 500"/>
  </g>
</svg>"""
    
    # Write to file
    output_path = 'static/images/board.svg'
    with open(output_path, 'w') as f:
        f.write(svg_content)
    
    print(f"Generated map: {output_path}")
    return svg_content

if __name__ == '__main__':
    generate_map()
