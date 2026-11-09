Create the backend application in Python which provides the visual testing of the pictures (screenshots).
Usage: checker.py file1 file2 - two arguments which are two files to compare
1. Application needs a configuration:
- input files directory - a path to the files being compared
- mode: text (default) - OCRs the files and compares the texts, 
visual - checks if the proper elements (like buttons, icons etc.) are visible on she screenshots.
2. Comparison should create the report file. For starters it should be a text file containing the listed differences between the texts on both screenshots. Something like diff tool, but that should be in a comprehensive way for people who read that. More important is if  the section in the second file exists and contains the same text (list the difference) 
It should also show that sections are in different positions.

First generate the text mode only.

Second part
Visual comparisons of the pictures. Do not OCR the text. Compare pictures with some tolerance to the blocks on it. Blocks of texts, widgets (buttons, forms etc.). Mark with red color (rectangles, lines) on the second picture what is different.
If it's not an optimal solution, prepare the report picture with the differences marked.