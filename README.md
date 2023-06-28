# Proper Scoring Rules for calibration.

This repository contains the code for doing calibration on multi-class and binary classification using various approaches. The core functionality was written by Niko Brummer. Sergio Alvarez and I later added various methods and scripts to experiment with them. Further, I have another repository called [expected_cost](https://github.com/luferrer/expected_cost.git) with lots of examples on how to use the libraries in this repository. 

## How to install

```
pip install psrcal
```

When you do that, torch, matplotlib and other libraries will also be installed, unless you already have the required versions in your system. It does not install joblib and ternary, which are only needed to run the scripts in the experiments dir. If you want to run those scripts, you can install those two packages separately. 

Alternatively, if you want the latest version of the code, you can:

1. Clone the repository:  

   ```git clone https://github.com/luferrer/psr-calibration.git```

2. Install the requirements (this does install joblib and ternary since it assumes you are probably cloning the repo in order to run the scripts inside the experiments dir):  
   
   ```pip install -r requirements.txt```
   
3. Add the resulting top directory in your PYTHONPATH. In bash this would be:

   ```export PYTHONPATH=ROOT_DIR/psr-calibration:$PYTHONPATH```

where ROOT_DIR is the absolute path (or the relative path from the directory where you have the scripts or notebooks you want to run) to the top directory from where you did the clone above.

