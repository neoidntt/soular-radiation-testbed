import os
import tempfile
from Curvefit import load_data_from_file

text = 'LET,sigma\n0,0\n1,0.1\n1,0.2\n2,0.4\n2,0.5\n3,0.7\n'
with tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False) as f:
    f.write(text)
    path = f.name

try:
    data = load_data_from_file(path)
    print(data.to_string(index=False))
finally:
    os.unlink(path)
