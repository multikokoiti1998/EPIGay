# coding: utf-8

#from copyreg import dispatch_table
from math import nan, sqrt
#from operator import truediv
from pickle import TRUE
#from turtle import exitonclick
import numpy as np
import tkinter as tk
from tkinter import SE, filedialog
from PIL import Image
import nrrd
import tifffile
from numpy.lib.stride_tricks import sliding_window_view
import datetime
import multiprocessing
import time

def openTiffFileGUI(ttl: str)->str:
    """
    Gui for opening a tiff file
    return string
    """

    # GUIのファイル選択ダイアログを開く
    root = tk.Tk()
    root.withdraw()  # ルートウィンドウを非表示
    file_path = filedialog.askopenfilename(title=ttl, filetypes=[("TIFF files", "*.tiff *.tif")])

    return file_path


def openTiffFile(file_path):
  """
    Gray Scale Tiffファイルを開いてnumpy arrayにする.
    file_path: ファイルのパス

    Returns: numpy.ndarray: 画像データを含むNumPy配列。
                   配列の形状は (depth, height, width) となります。
                   データ型は np.uint16 になります。
  """
  try:
    with tifffile.TiffFile(file_path) as tif:
      image_data = tif.asarray()
      if image_data.ndim < 2:
        raise ValueError(f"2D以上の次元である必要があります: {image_data.ndim}")
      # 念のため、チャンネル数が1であることを確認 (グレースケール)
      if image_data.shape[-1] == 1:
        image_data = image_data[..., 0]
      return image_data

  except FileNotFoundError:
    print(f"エラー: ファイルが見つかりません: {file_path}")
    return None
  except Exception as e:
    print(f"エラー: TIFFファイルの読み込み中にエラーが発生しました: {e}")
    return None


def save_nrrd(data: np.ndarray, title="Save data in .nrrd", flip = False):
    """
    NumPyの3D配列をNRRD形式で保存し、保存先をファイルダイアログで指定します。

    Args:
        data (np.ndarray): 保存する3Dもしくは2D NumPy配列。4D以上や1Dは保存できない.
        flip: numpyはz,y,x順の配列. nrrdではx,y,z順として保存されるので,軸の入れ替えのON/Offのパラメータ
    """
    root = tk.Tk()
    root.withdraw()  # メインウィンドウを表示しない

    if flip == True:
        if data.ndim == 3:
            data = np.transpose(data, (2, 1, 0))
        elif data.ndim == 2:
            data = np.transpose(data, (1, 0))
        else:
            print('unsported dimension:' + str(data.ndim))
            return

    file_path = filedialog.asksaveasfilename(
        defaultextension=".nrrd",
        filetypes=[("NRRD files", "*.nrrd"), ("All files", "*.*")],
        title=title
    )

    if file_path:
        try:
            nrrd.write(file_path, data)
            print(f"Successfully saved NRRD file to: {file_path}")
        except Exception as e:
            print(f"Error saving NRRD file: {e}")

def calculate_distances(refarray, movarray, delta, pix_size = 0.25):
    """
        Calculate distance to agreement in each slice.
        refarray: reference images in numpy 3D array.
        movarray: moving images in numpy 3D array
        delta: tolerance of distance in mm
        pix_size: pixel size of the both images. 0.25 mm/pix is the default anf is for the Elekta iView EPID data.
    """
    start_time=time.perf_counter()
    # Calculate boundary of a search region
    margin_rate = 1.5
    distancemax = delta * margin_rate  #calculate DTA in range of delta * margin_rate
    deltapix =int(np.round(distancemax/pix_size + 0.5))  # from distancemax in mm to in pixels.

    # 3D配列の形状を取得
    shape = movarray.shape
    print(shape)
    if movarray.ndim != 3 or refarray.ndim != 3:
        print("reference image and moving image should be 3D array data.")
        print("reference image: " + str(refarray.ndim))
        print("moving image: " + str(movarray.ndim))
        exit()

    # 出力用の3次元配列を初期化
    distances = np.full(shape, np.inf).astype(np.float32)

    xmov = np.arange(shape[2])
    ymov = np.arange(shape[1])
    zmov = np.arange(shape[0])
    xmovmesh, ymovmesh, zmovmesh = np.meshgrid(xmov, ymov, zmov)
    move_grid = np.stack((zmovmesh.ravel(), ymovmesh.ravel(), xmovmesh.ravel()),axis=-1)

    # 配列内のすべての要素に対して距離を計算
    #z軸をstackしているのでz軸をfor分で回す
    for coord1 in move_grid:
        value1 = movarray[tuple(coord1)]
        #x,y,zが3つの値が入ったcoord1
        if refarray[tuple(coord1)] == value1: 
            distances[tuple(coord1)] = 0
            continue
        elif refarray[tuple(coord1)] > value1: overflag = True
        else : overflag = False
        #検索範囲の限界 0以上画像未満
        x_neg = coord1[2]-deltapix  if coord1[2]-deltapix > 0 else 0
        y_neg = coord1[1]-deltapix  if coord1[1]-deltapix > 0 else 0
        x_pos = coord1[2]+deltapix +1 if coord1[2]+deltapix +1 < shape[2] else shape[2]
        y_pos = coord1[1]+deltapix +1 if coord1[1]+deltapix +1 < shape[1] else shape[1]
        #region = refarray[coord1[0]:coord1[0]+1,y_neg:y_pos, x_neg:x_pos]

        xcoord = np.arange(x_neg, x_pos)
        ycoord = np.arange(y_neg, y_pos)
        xmesh, ymesh, zmesh = np.meshgrid(xcoord, ycoord, coord1[0])
        window_grid = np.stack((zmesh.ravel(), ymesh.ravel(), xmesh.ravel()),axis=-1)

        mindist = distancemax
        #Windw_grid内の座標で異なる符号を持つ座標を探す
        for target in window_grid:
            if overflag == True:
                if refarray[tuple(target)] <= value1:
                    tmp =np.sqrt(np.sum((target-coord1)**2))
                    mindist= min(mindist, tmp)
            else:
                if refarray[tuple(target)] >= value1:
                    tmp =np.sqrt(np.sum((target-coord1)**2))
                    mindist= min(mindist, tmp)

        distances[tuple(coord1)] = mindist
    print(distances.dtype)
    end_time=time.perf_counter()
    during_time=end_time-start_time
    print(f"経過時間:::{during_time}")
    return distances * pix_size  # transfer to values in mm




def calcAngleDifference(ref_array, mov_array, deltaangle=3, angle_step = 1.0):
    """
    calculation in angle
    ref_array, mov_array: numpy array. these array should have the same shape and be matched the angle each other. dtype = np.float or np.double.
    serach_region: serarch region of angle (number of slices)to find the same pixel value. Twist deltaangle become the maxmum angle difference. default 3 slices(angle steps).
    angle_step : angle difference beween slices. default 1.0 degree
    return: numpy array of angle difference
    """
    search_region= deltaangle * 2 
    shape = ref_array.shape
    angleIndex = np.array([s for s in range(shape[0])])
    #interp_angleIndex = np.array([y for y in range(shape[0]*2 -1)]) / 2
    angleDiff = np.full(shape, np.inf)
    #delta = int(np.round(delta*1.5 + 0.5))

    for x in range(shape[2]):
        for y in range(shape[1]):
            refAngle = ref_array[:,y:y+1,x:x+1].reshape((shape[0]))
            movAngle = mov_array[:,y:y+1,x:x+1].reshape((shape[0]))

            for i in range(shape[0]):
                v = movAngle[i]
                target_index= search_region
                lowindex = i -search_region 
                highindex = i + search_region + 1
                if i < search_region:
                    lowindex = 0
                    target_index = i 
                elif i > shape[0] -search_region:
                    highindex= shape[0]

                region = refAngle[lowindex:highindex]-v
                if np.count_nonzero(np.where(region == 0)) > 0:
                    angleDiff[i][y][x]=0
                    #angleDiff[i:i+1,y:y+1,x:x+1]=0
                    continue
                elif np.count_nonzero(np.where(region > 0))== 0 or np.count_nonzero(np.where(region < 0))== 0:
                    continue
                else:
                    big = np.array(np.where(region > 0, True, False))
                    # sliding_window_viewで窓を作成
                    windows = sliding_window_view(big, window_shape=2)

                    # 各窓とシーケンスを比較
                    # np.all(windows == seq, axis=1) で各窓がseqと完全に一致するかを判定
                    forward = np.all(windows == [True, False], axis=1)
                    forward = np.where(forward==True)[0]
                    backward = np.all(windows == [False,True], axis=1)
                    backward = np.where(backward == True)[0]             
                    
                    dist = np.inf
                    if forward.size >= 1:
                        indx = np.argmin(np.abs(forward-target_index))
                        forward_dist = forward[indx]-target_index
                        dist= forward_dist + angle_step * np.abs(region[forward[indx]]) /np.abs(region[forward[indx]] - region[forward[indx]+1])

                    if backward.size >= 1:
                        indx = np.argmin(np.abs(backward-target_index))
                        backward_dist = backward[indx]-target_index
                        dist = min(dist, float(backward_dist) + angle_step * np.abs(region[backward[indx]]) /np.abs(region[backward[indx]] - region[backward[indx]+1]))

                    if dist == np.inf:
                        print("no candidate for dist was picked up in the region!")

                    angleDiff[i][y][x]= np.abs(dist).astype(np.float32)

    angleDiff = np.where(angleDiff==np.inf,search_region, angleDiff)
    return angleDiff

def calculateDoseDiff(RefArray, MovArray):
    if RefArray.shape != MovArray.shape:
        print("The moving image have different size from the reference image.")
        print("Reference:")
        print(RefArray.shape)
        print("Moving:")
        print(MovArray.shape)
        exit()
    
    return (MovArray - RefArray).astype(np.float32)

def worker(ind, func, args,q):
    """
    各関数を実行し、結果をキューに入れるワーカー関数
    """
    result = func(*args)
    try:
        q.put({"index":ind, "data":result})
    except Exception as e:
        print(f"プロセス1でエラーが発生しました: {e}")
        # エラー情報をキューに入れて親に伝えることも可能
        q.put((args, str(e)))

    print(ind + ' returned ' + str(datetime.datetime.now()))
    if q.full(): print(ind + ' Queue FULL')
   

def GammaAnalysis3DOF(refarray, movarray, deltadd=3, deltadta=2, deltaangle=3):
    """
    3DOFGamma add anglar difference to 2D gamma analysis.
    refarray: reference 3D image, numpy array.
    movarray: moving 3D image, should be analyized image. numpy array.
    deltadd: tolerance dose difference. default 3 %
    deltadta: tolerance distance-to-agreement. default 2 mm
    deltaangle: tolerance anglar difference. default 3 deg.
    """

    que = multiprocessing.Queue()
    processes=[]

    p1 = multiprocessing.Process(target=worker, args= ("dd", calculateDoseDiff, (refarray, movarray), que))
    processes.append(p1)
    p2 = multiprocessing.Process(target=worker , args=("dta", calculate_distances, (refarray, movarray, deltadta), que))
    processes.append(p2)
    p3 = multiprocessing.Process(target=worker, args=("ang",  calcAngleDifference, (refarray, movarray, deltaangle), que ))
    processes.append(p3)

    for p in processes:
        p.start()
        print(str(p) +'start')

    finished = 0
    while finished < len( processes):
        d = que.get()
        if d["index"] == "dd":   
            dd = d["data"]
            finished += 1
        elif  d["index"] == "dta":
           dta = d["data"]
           finished += 1
        elif d["index"] == "ang":
           ang = d["data"]
           finished += 1
        else : print("wrong index for results")

    print('DD:')
    print(dd)
    print('DTA:')
    print(dta)
    print('angle:')
    print(ang)

    for p in processes:
        print(str(p) +'join')
        p.join(timeout=30)

    gamma = np.sqrt(dd/deltadd * dd/deltadd + dta/deltadta * dta/deltadta + ang/deltaangle * ang/deltaangle)


    print(gamma)
    # dd, dta, ang,
    return  gamma


##
##  test functions
##

def test_savenrrd():
    # サンプルデータとして適当な3D NumPy配列を作成
    dummy_data = np.random.rand(32, 48, 64)  # 例: X64, Y48, Z32 のfloat型のデータ

    # 作成したデータをNRRD形式で保存（ファイルダイアログが開きます）
    save_nrrd(dummy_data,flip=True)


def test_calculation_distance():
    # サンプルデータ
    array1 = np.random.randint(0, 5, (4, 6, 6))  # ランダムな値を持つ3次元配列
    array2 = np.random.randint(0, 5, (4, 6, 6))  # ランダムな値を持つ3次元配列

    print("Array 1:")
    print(array1)
    print("Array 2:")
    print(array2)

    # 距離を計算
    distances = calculate_distances(array1, array2,2)

    # 結果を表示
    print("XY distance:")
    print(distances)


def test_calcAngleDifference():
   # ref_array = np.random.randint(0,9, (10,3,3))# ランダムな値を持つ3次元配列
   # mov_array = np.random.randint(0,9,(10,3,3))# ランダムな値を持つ3次元配列
    ref_array = np.array([[[4, 2, 0],[8, 1, 7],[3, 5, 3]],\
                [[2, 3, 8],[5, 5, 5],[8, 7, 4]],\
                [[1, 8, 5],[0, 7, 2],[8, 6, 1]],\
                [[7, 6, 5],[8, 0, 0],[7, 0 ,2]],\
                [[3, 8, 7],[8, 7, 7],[5, 5, 1]]])


    mov_array=np.array([[[7, 4, 3],[2, 4, 2],[7, 2, 8]],\
               [[2, 6, 7],[2, 0 ,5],[5, 5, 6]],\
               [[2, 3, 0],[4, 1, 7],[2, 6, 5]],\
               [[6, 6, 5],[1, 2, 4],[2, 3, 7]],\
               [[3, 1, 8],[2, 2, 3],[6, 8, 2]]])


    print('ref_array:')
    print(ref_array)
    print('mov_array:')
    print(mov_array)

    angle = calcAngleDifference(ref_array, mov_array)

    print('angle:')
    print(angle)

def test_GUI():
    print(openTiffFileGUI())

def test_openTiffFile():
    #f = "/home/at/Documents/file.tiff"
    f= "C://Users//omnip//Documents//Riho_insurrance_docs01.tif"
    array = openTiffFile(f)

    print('shape:')
    print(array.shape)
    print('array:')
    print(array)

def test_calculateDoseDiff():
    ref_array = np.array([[[4, 2, 0],[8, 1, 7],[3, 5, 3]],\
                [[2, 3, 8],[5, 5, 5],[8, 7, 4]],\
                [[1, 8, 5],[0, 7, 2],[8, 6, 1]],\
                [[7, 6, 5],[8, 0, 0],[7, 0 ,2]],\
                [[3, 8, 7],[8, 7, 7],[5, 5, 1]]])


    mov_array=np.array([[[7, 4, 3],[2, 4, 2],[7, 2, 8]],\
               [[2, 6, 7],[2, 0 ,5],[5, 5, 6]],\
               [[2, 3, 0],[4, 1, 7],[2, 6, 5]],\
               [[6, 6, 5],[1, 2, 4],[2, 3, 7]],\
               [[3, 1, 8],[2, 2, 3],[6, 8, 2]]])

    dif = calculateDoseDiff(ref_array, mov_array)
    print("dif.shape:")
    print(dif.shape)
    print("dif")
    print(dif)


def test_gammaAnalysis3dof():
    ref_array = np.array([[[4, 2, 0],[8, 1, 7],[3, 5, 3]],\
                [[2, 3, 8],[5, 5, 5],[8, 7, 4]],\
                [[1, 8, 5],[0, 7, 2],[8, 6, 1]],\
                [[7, 6, 5],[8, 0, 0],[7, 0 ,2]],\
                [[3, 8, 7],[8, 7, 7],[5, 5, 1]]], dtype=np.float32)


    mov_array=np.array([[[7, 4, 3],[2, 4, 2],[7, 2, 8]],\
               [[2, 6, 7],[2, 0 ,5],[5, 5, 6]],\
               [[2, 3, 0],[4, 1, 7],[2, 6, 5]],\
               [[6, 6, 5],[1, 2, 4],[2, 3, 7]],\
               [[3, 1, 8],[2, 2, 3],[6, 8, 2]]],dtype=np.float32)

    gam = GammaAnalysis3DOF(ref_array, mov_array)
    print("gamma result size:")
    print(gam.shape)
    print("gamma:")
    print(gam)

def test_GUI_OpenTiff_save():
    f = openTiffFileGUI()
    array = openTiffFile(f)
    save_nrrd(array, flip=True)

def test_CalcAngleDifference():

    ref_array= np.random.rand(12,3,3) * 10
    mov_array = np.random.rand(12,3,3)* 10
    delta = 2
    print("ref array:")
    print(ref_array)
    print("mov array:")
    print(mov_array)

    dist_array = calcAngleDifference(ref_array, mov_array, delta)

    print("dist array:")
    print(dist_array)

def test_all():
    
    #test_GUI()
    #test_openTiffFile()
    #test_calculateDoseDiff()
    #test_calculation_distance()
    #test_CalcAngleDifference()
    # test_gammaAnalysis3dof()
    #test_savenrrd()
    #test_GUI_OpenTiff_save()
    pass



# 
#  Main
#
#


if __name__ == '__main__':

    testing = False

    if testing == True:
        test_all()
    else:
        print(datetime.datetime.now())
        f = openTiffFileGUI('Open a plan tiff file')
        if f == "": exit()
        planarray = openTiffFile(f)

        f = openTiffFileGUI('Open a EPID tiff file')
        if f == "": exit()
        epidarray = openTiffFile(f)

        dd, dta, ang, gamma = GammaAnalysis3DOF(planarray, epidarray, deltadd=3, deltadta=2, deltaangle=3)
        print(datetime.datetime.now())
        save_nrrd(np.astype(gamma, np.float32),title= "Save the Gamma result.", flip=True)
        save_nrrd(np.astype(dd, np.float32), title="Save the Dose Difference result.", flip=True)
        save_nrrd(np.astype(dta, np.float32),title= "Save the Distance To Agreement result.", flip=True)
        save_nrrd(np.astype(ang, np.float32), title="Save the Angle to Agreement result.", flip=True)

#todo debug main
"""
ガンマインデックスの定式化Low et al., Med Phys 1998, DOI: 10.1118/1.598248
アルゴリズム実装Depuydt et al., Radiother Oncol 20023%/3mm閾値の臨床標準AAPM TG 218 (Miften et al., 2018)
角度次元を加えた3DOF拡張標準的な査読文献なし（独自拡張）
ガントリー角度許容値の参考値Rowshanfarzad et al., Med Phys 2013（±0.5°や±1°が使われる）
"""