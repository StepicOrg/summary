import os


def mkdir_and_cd(filename, suffix):
    dir_name = os.path.join(os.getcwd(),'{}_{}'.format(os.path.splitext(filename)[0], suffix))
    if not os.path.exists(dir_name):
        os.mkdir(dir_name)
    os.chdir(dir_name)


class Shape:
    width = None
    height = None

    def __init__(self, width, height):
        self.width = width
        self.height = height


class Human:
    x_min = None
    x_max = None
    w = None

    def __init__(self, x_min, x_max, w):
        self.x_min = x_min
        self.x_max = x_max
        self.w = w

    @staticmethod
    def union(lhs, rhs):
        x_min = min(lhs.x_min, rhs.x_min)
        x_max = max(lhs.x_max, rhs.x_max)
        w = x_max - x_min
        return Human(x_min=x_min, x_max=x_max, w=w)
