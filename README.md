This script extracts all the images from:
https://ajinmanga.net/

Works with website containing similar html/UI structure like:
https://w10.1punchman.com/
https://chainsawmann.com/

Currently, to extract from other websites, manual modification of the `BASE` variable and grep patterns in `url_down.sh` is required. 
Extraction for each chapter is done in parallel (32 threads currently), making it much faster (~4mins vs 2+hrs sequentially).