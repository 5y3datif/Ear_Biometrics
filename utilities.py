def load_dataset(dataset='AMI', target_size = (50, 180)):
  ### This function load ear-biometric datasets and reshape into specified size
  ##########

  if (dataset=='AMI'):
    # target_size = (246, 351) 
    data_path = 'https://github.com/Shujaat123/Ear_Biometrics/blob/main/datasets/AMI_dataset.zip?raw=true'
    filename = 'AMI_dataset.zip'
    src_dir = 'AMI_dataset'
    
    if(path.exists(filename)):
      !rm $filename
      print('existing file:', filename, ' has been deleted')
    print('downloading latest version of file:', filename)
    wget.download(data_path, filename)
    print('sucessfully downloaded')

    with ZipFile('AMI_dataset.zip', mode='r') as z:
        z.extractall()
    !ls

  elif (dataset=='IITD_dataset'):
    # target_size = (50, 180)
    data_path='https://github.com/Shujaat123/Ear_Biometrics/blob/main/datasets/IITD_Dataset.7z?raw=true'
    filename='IITD_Dataset.7z'
    src_dir = 'ear/processed/221'

    if(path.exists(filename)):
      !rm $filename
      print('existing file:', filename, ' has been deleted')
    print('downloading latest version of file:', filename)
    wget.download(data_path, filename)
    print('sucessfully downloaded')

    with py7zr.SevenZipFile('IITD_Dataset.7z', mode='r') as z:
        z.extractall()
    !ls

  else:
    print('Unknown dataset')


  images_name = listdir(src_dir)
  images_name_temp = []
  subjects = []
  for img_ind in range(0,len(images_name)):
    if(not(images_name[img_ind]=='Thumbs.db')):
      subjects.append(int(images_name[img_ind].split('_')[0]))
      images_name_temp.append(images_name[img_ind])

  images_name = images_name_temp
  images_name_ord = []
  subjects_ord = []

  sub_ind = sorted(range(len(subjects)),key=subjects.__getitem__)
  for pos, item in enumerate(sub_ind):
    images_name_ord.append(images_name[item])
    subjects_ord.append(subjects[item])

  images_name = images_name_ord
  subjects = subjects_ord

  print(subjects)
  ##########--MODIFICATION to rearange missing labels #############
  subjects_temp = np.array(subjects)
  unique_ids=np.unique(np.array(subjects))

  for pos, item in enumerate(unique_ids):
    subjects_temp[subjects==item] = pos+1

  subjects = list(subjects_temp)
  ################################################################
  print(images_name)

  img_ind = 0
  ear_images = []
  sub_labels = [];

  for sub_ind in range(0,len(subjects)):
    img_path = src_dir+'/'+images_name[sub_ind]
    ear_img = (plt.imread(img_path))/255

    ear_img = Image.open(img_path)
    ear_img = ear_img.resize(target_size, Image.ANTIALIAS)
    ear_img = np.asarray(ear_img).astype(np.float32)/255
    
    if(len(ear_img.shape)<3):
      ear_img = np.expand_dims(ear_img,axis=0)
    else:
      ear_img = np.transpose(ear_img,(2,0,1)) # moving channel dim from 3rd position:(Row, Col, Channels) to 1st position:(Channels, Row, Col)

    ear_images.append(ear_img)
    sub_labels.append(subjects[sub_ind]-1)

  ear_images = np.array(ear_images)
  sub_labels = np.array(sub_labels)

  print(ear_images.shape)
  print(sub_labels.shape)

  return ear_images, sub_labels