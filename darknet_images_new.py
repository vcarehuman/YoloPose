import cv2
import time
import numpy as np
from random import randint
import argparse
from google.colab.patches import cv2_imshow
import imutils
import os

parser = argparse.ArgumentParser(description='Run keypoint detection')
parser.add_argument("--device", default="gpu", help="Device to inference on")
parser.add_argument("--image_file", default="group.jpg", help="Input image")
parser.add_argument("--image_folder",  help="Input folder")
parser.add_argument("--protoFile", default="group.jpg", help="Input image")
parser.add_argument("--weightsFile", default="group.jpg", help="Input image")
parser.add_argument("--thr", default=0.2, type=float, help="confidence threshold to filter out weak detections")

args = parser.parse_args()


protoFile = args.protoFile
weightsFile = args.weightsFile
nPoints = 18
# COCO Output Format
keypointsMapping = ['Nose', 'Neck', 'R-Sho', 'R-Elb', 'R-Wr', 'L-Sho', 'L-Elb', 'L-Wr', 'R-Hip', 'R-Knee', 'R-Ank', 'L-Hip', 'L-Knee', 'L-Ank', 'R-Eye', 'L-Eye', 'R-Ear', 'L-Ear']

POSE_PAIRS = [[1,2], [1,5], [2,3], [3,4], [5,6], [6,7],
              [1,8], [8,9], [9,10], [1,11], [11,12], [12,13],
              [1,0], [0,14], [14,16], [0,15], [15,17],
              [2,17], [5,16] ]

# index of pafs correspoding to the POSE_PAIRS
# e.g for POSE_PAIR(1,2), the PAFs are located at indices (31,32) of output, Similarly, (1,5) -> (39,40) and so on.
mapIdx = [[31,32], [39,40], [33,34], [35,36], [41,42], [43,44],
          [19,20], [21,22], [23,24], [25,26], [27,28], [29,30],
          [47,48], [49,50], [53,54], [51,52], [55,56],
          [37,38], [45,46]]

colors = [ [0,100,255], [0,100,255], [0,255,255], [0,100,255], [0,255,255], [0,100,255],
         [0,255,0], [255,200,100], [255,0,255], [0,255,0], [255,200,100], [255,0,255],
         [0,0,255], [255,0,0], [200,200,0], [255,0,0], [200,200,0], [0,0,0]]


# Labels of Network.
classNames = { 15: 'person'}


def findPeople(modelForPersonDetection,image1):
# Load image fro
    personList = []
    frame_resized = cv2.resize(image1,(300,300)) # resize frame for prediction
    heightFactor = image1.shape[0]/300.0
    widthFactor = image1.shape[1]/300.0 
    # MobileNet requires fixed dimensions for input image(s)
    # so we have to ensure that it is resized to 300x300 pixels.
    # set a scale factor to image because network the objects has differents size. 
    # We perform a mean subtraction (127.5, 127.5, 127.5) to normalize the input;
    # after executing this command our "blob" now has the shape:
    # (1, 3, 300, 300)
    blob = cv2.dnn.blobFromImage(frame_resized, 0.007843, (300, 300), (127.5, 127.5, 127.5), False)
    #Set to network the input blob 
    modelForPersonDetection.setInput(blob)
    #Prediction of network
    detections = modelForPersonDetection.forward()

    frame_copy = image1.copy()
    frame_copy2 = image1.copy()
    #Size of frame resize (300x300)
    cols = frame_resized.shape[1] 
    rows = frame_resized.shape[0]

     
    opacity = 0.3
    cv2.addWeighted(frame_copy, opacity, image1, 1 - opacity, 0, image1)

    for i in range(detections.shape[2]):
        confidence = detections[0, 0, i, 2] #Confidence of prediction 
        if confidence > args.thr: # Filter prediction 
            class_id = int(detections[0, 0, i, 1]) # Class label

            # Object location 
            xLeftBottom = int(detections[0, 0, i, 3] * cols) 
            yLeftBottom = int(detections[0, 0, i, 4] * rows)
            xRightTop   = int(detections[0, 0, i, 5] * cols)
            yRightTop   = int(detections[0, 0, i, 6] * rows)

            xLeftBottom_ = int(widthFactor * xLeftBottom) 
            yLeftBottom_ = int(heightFactor* yLeftBottom)
            xRightTop_   = int(widthFactor * xRightTop)
            yRightTop_   = int(heightFactor * yRightTop)
            cv2.rectangle(image1, (xLeftBottom_, yLeftBottom_), (xRightTop_, yRightTop_),(0,0,255))
            #person = [xLeftBottom_, yLeftBottom_ ,xLeftBottom_ , yLeftBottom_]
            personList.append([[xLeftBottom_, yLeftBottom_], [xRightTop_, yRightTop_], (yLeftBottom_ -yRightTop_) * (xLeftBottom_ -xRightTop_)] )
    return  personList   
            


def getKeypoints(probMap, threshold=0.1):

    mapSmooth = cv2.GaussianBlur(probMap,(3,3),0,0)

    mapMask = np.uint8(mapSmooth>threshold)
    keypoints = []

    #find the blobs
    contours, _ = cv2.findContours(mapMask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    #for each blob find the maxima
    for cnt in contours:
        blobMask = np.zeros(mapMask.shape)
        blobMask = cv2.fillConvexPoly(blobMask, cnt, 1)
        maskedProbMap = mapSmooth * blobMask
        _, maxVal, _, maxLoc = cv2.minMaxLoc(maskedProbMap)
        keypoints.append(maxLoc + (probMap[maxLoc[1], maxLoc[0]],))

    return keypoints


# Find valid connections between the different joints of a all persons present
def getValidPairs(output,frameWidth,frameHeight,detected_keypoints):
    valid_pairs = []
    invalid_pairs = []
    n_interp_samples = 10
    paf_score_th = 0.1
    conf_th = 0.7
    # loop for every POSE_PAIR
    for k in range(len(mapIdx)):
        # A->B constitute a limb
        pafA = output[0, mapIdx[k][0], :, :]
        pafB = output[0, mapIdx[k][1], :, :]
        pafA = cv2.resize(pafA, (frameWidth, frameHeight))
        pafB = cv2.resize(pafB, (frameWidth, frameHeight))

        # Find the keypoints for the first and second limb
        candA = detected_keypoints[POSE_PAIRS[k][0]]
        candB = detected_keypoints[POSE_PAIRS[k][1]]
        nA = len(candA)
        nB = len(candB)

        # If keypoints for the joint-pair is detected
        # check every joint in candA with every joint in candB
        # Calculate the distance vector between the two joints
        # Find the PAF values at a set of interpolated points between the joints
        # Use the above formula to compute a score to mark the connection valid

        if( nA != 0 and nB != 0):
            valid_pair = np.zeros((0,3))
            for i in range(nA):
                max_j=-1
                maxScore = -1
                found = 0
                for j in range(nB):
                    # Find d_ij
                    d_ij = np.subtract(candB[j][:2], candA[i][:2])
                    norm = np.linalg.norm(d_ij)
                    if norm:
                        d_ij = d_ij / norm
                    else:
                        continue
                    # Find p(u)
                    interp_coord = list(zip(np.linspace(candA[i][0], candB[j][0], num=n_interp_samples),
                                            np.linspace(candA[i][1], candB[j][1], num=n_interp_samples)))
                    # Find L(p(u))
                    paf_interp = []
                    for k in range(len(interp_coord)):
                        paf_interp.append([pafA[int(round(interp_coord[k][1])), int(round(interp_coord[k][0]))],
                                           pafB[int(round(interp_coord[k][1])), int(round(interp_coord[k][0]))] ])
                    # Find E
                    paf_scores = np.dot(paf_interp, d_ij)
                    avg_paf_score = sum(paf_scores)/len(paf_scores)

                    # Check if the connection is valid
                    # If the fraction of interpolated vectors aligned with PAF is higher then threshold -> Valid Pair
                    if ( len(np.where(paf_scores > paf_score_th)[0]) / n_interp_samples ) > conf_th :
                        if avg_paf_score > maxScore:
                            max_j = j
                            maxScore = avg_paf_score
                            found = 1
                # Append the connection to the list
                if found:
                    valid_pair = np.append(valid_pair, [[candA[i][3], candB[max_j][3], maxScore]], axis=0)

            # Append the detected connections to the global list
            valid_pairs.append(valid_pair)
        else: # If no keypoints are detected
            print("No Connection : k = {}".format(k))
            invalid_pairs.append(k)
            valid_pairs.append([])
    return valid_pairs, invalid_pairs



# This function creates a list of keypoints belonging to each person
# For each detected valid pair, it assigns the joint(s) to a person
def getPersonwiseKeypoints(valid_pairs, invalid_pairs,keypoints_list):
    # the last number in each row is the overall score
    personwiseKeypoints = -1 * np.ones((0, 19))

    for k in range(len(mapIdx)):
        if k not in invalid_pairs:
            partAs = valid_pairs[k][:,0]
            partBs = valid_pairs[k][:,1]
            indexA, indexB = np.array(POSE_PAIRS[k])

            for i in range(len(valid_pairs[k])):
                found = 0
                person_idx = -1
                for j in range(len(personwiseKeypoints)):
                    if personwiseKeypoints[j][indexA] == partAs[i]:
                        person_idx = j
                        found = 1
                        break

                if found:
                    personwiseKeypoints[person_idx][indexB] = partBs[i]
                    personwiseKeypoints[person_idx][-1] += keypoints_list[partBs[i].astype(int), 2] + valid_pairs[k][i][2]

                # if find no partA in the subset, create a new subset
                elif not found and k < 17:
                    row = -1 * np.ones(19)
                    row[indexA] = partAs[i]
                    row[indexB] = partBs[i]
                    # add the keypoint_scores for the two keypoints and the paf_score
                    row[-1] = sum(keypoints_list[valid_pairs[k][i,:2].astype(int), 2]) + valid_pairs[k][i][2]
                    personwiseKeypoints = np.vstack([personwiseKeypoints, row])
    return personwiseKeypoints

def processImage(image1,imageName,modelForPersonDetection):
    frameWidth = image1.shape[1]
    frameHeight = image1.shape[0]

    # Fix the input Height and get the width according to the Aspect Ratio
    inHeight = 368
    inWidth = int((inHeight/frameHeight)*frameWidth)

    inpBlob = cv2.dnn.blobFromImage(image1, 1.0 / 255, (inWidth, inHeight),
                              (0, 0, 0), swapRB=False, crop=False)

    net.setInput(inpBlob)
    output = net.forward()
    print("Time Taken in forward pass = {}".format(time.time() - t))

    detected_keypoints = []
    keypoints_list = np.zeros((0,3))
    keypoint_id = 0
    threshold = 0.1
    pointsWithPartCollection = []
    pointsWithParts = []
    for part in range(nPoints):
        probMap = output[0,part,:,:]
        probMap = cv2.resize(probMap, (image1.shape[1], image1.shape[0]))
        keypoints = getKeypoints(probMap, threshold)
        print("Keypoints - {} : {}".format(keypointsMapping[part], keypoints))
        if "Elb" in keypointsMapping[part] or "Wr" in keypointsMapping[part]:
            pointsWithParts = [keypointsMapping[part],[keypoints[0][0],keypoints[0][1]]]
            pointsWithPartCollection.append(pointsWithParts)

        keypoints_with_id = []
        for i in range(len(keypoints)):
            keypoints_with_id.append(keypoints[i] + (keypoint_id,))
            keypoints_list = np.vstack([keypoints_list, keypoints[i]])
            keypoint_id += 1

        detected_keypoints.append(keypoints_with_id)


    frameClone = image1.copy()
    

    counter = 0
    valid_pairs, invalid_pairs = getValidPairs(output,frameWidth,frameHeight,detected_keypoints)
    print("pointsWithPartCollection",pointsWithPartCollection)
    personwiseKeypoints = getPersonwiseKeypoints(valid_pairs, invalid_pairs,keypoints_list)
    pairWiseKeyPointsFound = []
    pairWiseKeyPointsFoundCollection = []
    pointsNotFoundInPairs = []
    for i in range(17):
        for n in range(len(personwiseKeypoints)):
            index = personwiseKeypoints[n][np.array(POSE_PAIRS[i])]
            if -1 in index:
                continue
            B = np.int32(keypoints_list[index.astype(int), 0])
            A = np.int32(keypoints_list[index.astype(int), 1])
            

            if ("Elb" in keypointsMapping[POSE_PAIRS[i][0]]) or ("Wr" in keypointsMapping[POSE_PAIRS[i][0]]):
                pairWiseKeyPointsFound = [keypointsMapping[POSE_PAIRS[i][0]],[B[0],A[0]]]
                pairWiseKeyPointsFoundCollection.append(pairWiseKeyPointsFound)
            
            if ("Elb" in keypointsMapping[POSE_PAIRS[i][1]]) or ("Wr" in keypointsMapping[POSE_PAIRS[i][1]]):
                pairWiseKeyPointsFound = [keypointsMapping[POSE_PAIRS[i][1]],[B[1],A[1]]]
                pairWiseKeyPointsFoundCollection.append(pairWiseKeyPointsFound)

            #cropping
            if "Elb" in keypointsMapping[POSE_PAIRS[i][0]] and "Wr" in keypointsMapping[POSE_PAIRS[i][1]]:
                #cropping logic
                distance = ((((B[1] - B[0] )**2) + ((A[1]-A[0])**2) )**0.5)
                print("distance",distance)
                height, width = frameClone.shape[:2]
                y1  = 0 if int(A[1]-distance)  < 0 else int(A[1]-distance)  
                y2  = height if int(A[1]+distance) > height else int(A[1]+distance) 
                x1  =  0 if int(B[1]-distance) < 0 else int(B[1]-distance)
                x2  =  width if int(B[1]+distance) > width else int(B[1]+distance)
                print("y1,y2,x1,x2", y1,y2,x1,x2)
                croppedImage = frameClone[y1:y2,x1:x2]
                imgname = imageName.rsplit( ".", 1 )[ 0 ] + "_" + str(counter)+".jpg";
                print(imgname)
                cv2.imwrite(args.image_folder+imgname , croppedImage)
                counter = counter + 1
                #saving logic
                
            

    # code for finding the points not in pair
    pointFound = False
    for i in range(len(pointsWithPartCollection)):
        for j in range(len(pairWiseKeyPointsFoundCollection)):
            if str(pointsWithPartCollection[i][0]) == (pairWiseKeyPointsFoundCollection[j][0]):
                if pointsWithPartCollection[i][1] == pairWiseKeyPointsFoundCollection[j][1]:
                    pointFound = True
                    break
        if pointFound == False:
            pointsNotFoundInPairs.append(pointsWithPartCollection[i])
        else:
            pointFound = False

    personList = findPeople(modelForPersonDetection, image1)
    #finding the right person box for the point that are not found in pairs
    for i in range(len(pointsNotFoundInPairs)):
        for j in range(len(personList)):
            if pointsNotFoundInPairs[i][1][0] > personList[j][0][0] and pointsNotFoundInPairs[i][1][0] < personList[j][1][0] and pointsNotFoundInPairs[i][1][1] > personList[j][0][1]  and pointsNotFoundInPairs[i][1][1] < personList[j][1][1]: 
                print("pointsNotFoundInPairs",pointsNotFoundInPairs[i])
                print("personList",personList[j])
                print("pointsNotFoundInPairs[i][1][0] > personList[j][0][0]",pointsNotFoundInPairs[i][1][0],personList[j][0][0])
                #print("personList[j][0][0]",personList[j][0][0])
                print("pointsNotFoundInPairs[i][1][0] > personList[j][1][0]",pointsNotFoundInPairs[i][1][0],personList[j][1][0])
                #print("personList[j][1][0]",personList[j][1][0])
                print("pointsNotFoundInPairs[i][1][1] < personList[j][0][1]",pointsNotFoundInPairs[i][1][1],personList[j][0][1])
                #print("personList[j][0][1]",personList[j][0][1])
                print("pointsNotFoundInPairs[i][1][1] < personList[j][1][1]",pointsNotFoundInPairs[i][1][1],personList[j][1][1])
                #print("personList[j][1][1]",personList[j][1][1]) 
                print("----------------------------------------------") 
                
                x1=int(personList[j][0][0])
                x2=int(personList[j][1][0])
                y1=int(int(personList[j][0][1]))
                y2=int(int(personList[j][1][1]))
                distance = (x2 - x1) /3
                distance = distance if distance>0 else distance*-1
                print(distance)
                print(pointsNotFoundInPairs[i][1][1],pointsNotFoundInPairs[i][1][0])
                y1  = 0 if int(pointsNotFoundInPairs[i][1][1]-distance)  < 0 else int(pointsNotFoundInPairs[i][1][1]-distance)  
                y2  = height if int(pointsNotFoundInPairs[i][1][1]+distance) > height else int(pointsNotFoundInPairs[i][1][1]+distance) 
                x1  =  0 if int(pointsNotFoundInPairs[i][1][0]-distance) < 0 else int(pointsNotFoundInPairs[i][1][0]-distance)
                x2  =  width if int(pointsNotFoundInPairs[i][1][0]+distance) > width else int(pointsNotFoundInPairs[i][1][0]+distance)
                croppedImage = frameClone[y1:y2,x1:x2]
                imgname = imageName.rsplit( ".", 1 )[ 0 ] + "_" + str(counter)+".jpg";
                print(imgname)
                cv2.imwrite(args.image_folder+imgname , croppedImage)
                counter = counter + 1


#print("pointsNotFoundInPairs",pointsNotFoundInPairs)         
#cv2.imwrite("result1.jpg" , frameClone)
#cv2.waitKey(0)

t = time.time()
net = cv2.dnn.readNetFromCaffe(protoFile, weightsFile)
if args.device == "cpu":
    net.setPreferableBackend(cv2.dnn.DNN_TARGET_CPU)
    print("Using CPU device")
elif args.device == "gpu":
    net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
    net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
    print("Using GPU device")
#Load the Caffe model 
modelForPersonDetection = cv2.dnn.readNetFromCaffe("/content/gdrive/MyDrive/MobileNetSSDModel/MobileNetSSD_deploy.prototxt", "/content/gdrive/MyDrive/MobileNetSSDModel/MobileNetSSD_deploy.caffemodel")

#image1 = cv2.imread(args.image_folder)
#predictor = Predictor(weights_path='fpn_inception.h5')
#print(predictor)
for filename in os.listdir(args.image_folder):
    print("filename",filename)
    img = cv2.imread(os.path.join(args.image_folder,filename))
    processImage(img,filename,modelForPersonDetection)




