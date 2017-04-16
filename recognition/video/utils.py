from typing import List

from scipy.signal import medfilt


class Rectangle(object):
    def __init__(self, x=0, y=0, w=0, h=0):
        self.x = x
        self.y = y
        self.w = w
        self.h = h

    def is_empty(self):
        return self.w == 0 or self.h == 0

    @staticmethod
    def from_rectangle(rectangle):
        return Rectangle(rectangle.x, rectangle.y, rectangle.w, rectangle.h)


def median_filter_rectangles(rectangles: List[Rectangle], kernel_size: int = 15) -> List[Rectangle]:
    real_rects_existance = list(map(lambda rect: 0 if rect.is_empty else 1, rectangles))
    smoothed_rects_existance = list(map(round, medfilt(real_rects_existance, kernel_size)))
    result = []
    for i, (real, smoothed) in enumerate(zip(real_rects_existance, smoothed_rects_existance)):
        if real == 0 and smoothed == 1:
            rectangle = interpolate_rectangle(rectangles, i)
        else:
            rectangle = Rectangle.from_rectangle(rectangles[i])
        result.append(rectangle)
    return result

def interpolate_rectangle(rectangles: List[Rectangle], index: int) -> Rectangle:
    left_rectangle = None
    for i in range(index - 1, 0, -1):
        if not rectangles[i].is_empty():
            left_rectangle = rectangles[i]
            break

    right_rectangle = None
    for i in range(index + 1, len(rectangles)):
        if not rectangles[i].is_empty():
            right_rectangle = rectangles[i]
            break

    if not left_rectangle:
        return Rectangle.from_rectangle(right_rectangle)

    if not right_rectangle:
        return Rectangle.from_rectangle(left_rectangle)

    def average(a, b):
        return (a + b) // 2

    return Rectangle(x=average(left_rectangle.x, right_rectangle.x),
                     y=average(left_rectangle.y, right_rectangle.y),
                     h=average(left_rectangle.h, right_rectangle.h),
                     w=average(left_rectangle.w, right_rectangle.w))
