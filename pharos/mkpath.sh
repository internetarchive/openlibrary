#!/bin/bash
# script to print list of important paths
echo
echo templates
echo type
echo tour
python2.5 run.py ls templates | grep -v brewster
python2.5 run.py ls type | grep -v brewster
echo about
python2.5 run.py ls about
echo macros
python2.5 run.py ls macros
echo dev/docs
python2.5 run.py ls dev/docs
echo b/adventures_of_Tom_Sawyer_0
echo b/adventures_of_Tom_Sawyer_1
echo b/adventures_of_Tom_Sawyer_2
echo b/Adventures_of_Finn_6
echo b/writings_of_Mark_Twain_54
echo b/Sketches_0
echo b/Adventures_of_Finn_6
echo b/Heartbreaking_of_Genius_1
echo b/heartbreaking_of_genius
echo b/heartbreaking_of_genius_1

