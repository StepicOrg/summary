from typing import List

import cv2
import dlib
import pywt
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

    def get_points(self):
        return (self.x, self.y), (self.x + self.w, self.y + self.h)

    @staticmethod
    def union(lhs_rect, rhs_rect):
        if lhs_rect.is_empty():
            return Rectangle.from_rectangle(rhs_rect)

        if rhs_rect.is_empty():
            return Rectangle.from_rectangle(rhs_rect)

        new_x = min(lhs_rect.x, rhs_rect.x)
        new_y = min(lhs_rect.y, rhs_rect.y)
        new_w = max(lhs_rect.x + lhs_rect.w, rhs_rect.x + rhs_rect.w) - new_x
        new_h = max(lhs_rect.y + lhs_rect.h, rhs_rect.y + rhs_rect.h) - new_y
        return Rectangle(x=new_x, y=new_y, w=new_w, h=new_h)

    @staticmethod
    def is_intersect(lhs_rect, rhs_rect):
        lp1, lp2 = lhs_rect.get_points()
        rp1, rp2 = rhs_rect.get_points()

        if rp2[1] < lp1[1] or rp1[0] > lp2[0] or rp1[1] > lp2[1] or rp2[0] < lp1[0]:
            return False

        return True

    def __repr__(self):
        return 'rectangle: x = {}; y = {}; w = {}; h = {};'.format(self.x, self.y, self.w, self.h)



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

def get_rectangle_with_human_dlib(image) -> Rectangle:
    height, width = image.shape
    detector = dlib.get_frontal_face_detector()
    dets = detector(image, 1)
    if len(dets) == 0:
        return Rectangle()
    det = dets[0]
    x = det.left()
    w = det.right() - x
    # new params
    center_x = x + w/2
    x_coef = 4
    x = max(0, center_x - x_coef*(w/2))
    w = min(x_coef*w, (width - 1) - x)
    return Rectangle(x=int(x), y=0, w=int(w), h=height-1)

def image_diff_canny(lhs_image, rhs_image, th1=100, th2=200) -> int:
    lhs_edges = cv2.Canny(lhs_image, th1, th2)
    rhs_edges = cv2.Canny(rhs_image, th1, th2)
    return cv2.absdiff(lhs_edges, rhs_edges).sum()

def image_diff_dwt(lhs_image, rhs_image) -> int:
    _, (lhs_LH, lhs_HL, lhs_HH) = pywt.dwt2(lhs_image, 'haar')
    _, (rhs_LH, rhs_HL, rhs_HH) = pywt.dwt2(rhs_image, 'haar')
    d1 = cv2.absdiff(lhs_LH, rhs_LH).sum()
    d2 = cv2.absdiff(lhs_HL, rhs_HL).sum()
    d3 = cv2.absdiff(lhs_HH, rhs_HH).sum()
    return d1 + d2 + d3

def image_diff_abs(lhs_image, rhs_image) -> int:
    return cv2.absdiff(lhs_image, rhs_image).sum()

def image_diff_color_hist(lhs_image, rhs_image) -> int:
    diff = 0
    for i in range(lhs_image.shape[2] if len(lhs_image.shape)==3 else 1):
        lhs_hist = cv2.calcHist([lhs_image], [i], None, [32], [0, 256])
        rhs_hist = cv2.calcHist([rhs_image], [i], None, [32], [0, 256])
        diff += cv2.absdiff(lhs_hist, rhs_hist).sum()
    return diff

def get_rectangle_with_human_opencv(image, haar_cascade_path) -> Rectangle:
    cascade = cv2.CascadeClassifier(haar_cascade_path)
    if cascade.empty():
        return Rectangle()
    rects = cascade.detectMultiScale(image)
    if len(rects) == 0:
        return Rectangle()
    print(rects)

