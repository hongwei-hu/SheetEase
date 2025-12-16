# Author: huhongwei 306463233@qq.com
# MIT License
from ..exceptions import DuplicateFieldError
from collections import Counter

def read_cell_values(sheet, row_index):
    return [cell.value for cell in sheet[row_index]]

def check_repeating_values(values):
    # O(n) 复杂度替换原 O(n^2)，保持行为
    counter = Counter(values)
    dup = {k for k, c in counter.items() if c > 1}
    if dup:
        raise DuplicateFieldError(dup)



