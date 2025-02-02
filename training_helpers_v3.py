import numpy as np
import torch
from torch.utils.data import TensorDataset, DataLoader
import torch.nn
import torch.nn.functional
import torch.optim
from torchvision import models #just for debugging
from  sklearn.model_selection import train_test_split, StratifiedShuffleSplit, ShuffleSplit, StratifiedKFold, KFold # KFold is added by Atif
from sklearn.utils import shuffle
from torchvision import transforms
from spc import SupervisedContrastiveLoss
import sys

def to_categorical(y, num_classes):
    """ 1-hot encodes a tensor """
    return np.eye(num_classes, dtype='uint8')[y]

# manaul training
def train_one_epoch(training_loader, validation_loader,
                    num_training_samples, num_validation_samples,
                    input_shape=(351, 246, 3), num_classes=100, 
                    model_parameters={'model_type': "Encoder+Classifier", 
                                      'model': None, 'num_filters': 8,
                                      'optimizer': None,
                                      'loss_fn_type': 'contrastive',
                                      'loss_fn': torch.nn.CrossEntropyLoss(), 
                                      'loss_fn2': torch.nn.MSELoss(), 
                                      'lambda1': 0.5, 'lambda2': 0.5},
                    train_device='cuda'):    
    num_filters=model_parameters['num_filters']
    model_type=model_parameters['model_type']
    model=model_parameters['model']
    optimizer=model_parameters['optimizer']
    loss_fn_type=model_parameters['loss_fn_type']
    loss_fn=model_parameters['loss_fn'] 
    loss_fn2=model_parameters['loss_fn2']
    lambda1=model_parameters['lambda1']
    lambda2=model_parameters['lambda1']
    
    # training metrics
    train_encoder_loss = 0
    train_classifier_loss = 0
    train_loss = 0
    train_correct = 0

    # validation metrics
    valid_encoder_loss = 0
    valid_classifier_loss = 0
    valid_loss = 0
    valid_correct = 0


    # Here, we use enumerate(training_loader) instead of
    # iter(training_loader) so that we can track the batch
    # index and do some intra-epoch reporting
    model.train(True)
    if(model_type=='Classifier'):
      lambda1=1;
      lambda2=0;
      ct = 0
      for child in model.children():
        ct += 1
        if ct == 2: # turn off weigth update for Encoder and Decoder modules
            for param in child.parameters():
                param.requires_grad = True
        else:
            for param in child.parameters():
                param.requires_grad = False
    elif(model_type=='Encoder+Classifier'):
      lambda1=1;
      lambda2=0;
      ct = 0
      for child in model.children():
        ct += 1
        if ct == 3: # turn off weigth update for Decoder module only
            for param in child.parameters():
                param.requires_grad = False
        else:
            for param in child.parameters():
                param.requires_grad = True
    elif(model_type=='AutoEncoder'):
      lambda1=0;
      lambda2=1;
      ct = 0
      for child in model.children():
        ct += 1
        if ct == 2: # turn off weigth update for Classifier module
            for param in child.parameters():
                param.requires_grad = False
        else:
            for param in child.parameters():
                param.requires_grad = True
    elif(model_type=='DeepLSE'): # train full-network
      for child in model.children():
        for param in child.parameters():
            param.requires_grad = True
    else:
      print('Incorrect choice for model configuration')

    for i, data in enumerate(training_loader,0):
        # Every data instance is an input + label pair
        train_input, train_label = data

        #if loss_fn_type == "contrastive": 
        #	train_input = torch.cat((train_input, train_input))
        #	train_label = train_label.repeat(2)
                
        train_label_one_hot = torch.tensor(to_categorical(y=train_label, num_classes=num_classes)).float()
        if len(train_label_one_hot.shape)==1:
        	train_label_one_hot = train_label_one_hot.unsqueeze(dim=0)
        
        train_input = train_input.to(torch.device(train_device))
        train_label = train_label.to(torch.device(train_device))
        train_label_one_hot = train_label_one_hot.to(torch.device(train_device))
        
        # Zero your gradients for every batch!
        #optimizer.zero_grad()
        # optimizer_classifier.zero_grad()

        # Make predictions for this batch
        train_output, decoded_input, encoded_output = model(train_input)
        encoded_output = torch.reshape(encoded_output,(encoded_output.shape[0],-1))
        # Compute the loss and its gradients
        classifier_loss = loss_fn(train_output, train_label_one_hot)
        if loss_fn_type == 'contrastive':
          encoder_loss = loss_fn2(encoded_output, train_label)
        else:
          encoder_loss = loss_fn2(train_input, decoded_input)
        
        loss = (lambda1)*classifier_loss + (lambda2)*encoder_loss
        loss.backward()

        # Adjust learning weights
        optimizer.step()
        # optimizer_classifier.step()

        # Gather data and report
        train_classifier_loss += classifier_loss.item()
        train_encoder_loss += encoder_loss.item()
        train_loss += loss.item()
        for batch_count in range(train_output.shape[0]):
          if(torch.argmax(train_output[batch_count,:]) == torch.argmax(train_label_one_hot[batch_count,:])):
            train_correct += 1
    # print('training epoch complete')
    # Here, we use enumerate(validation_loader) instead of
    # iter(validation_loader) so that we can track the batch
    # index and do some intra-epoch reporting
    model.train(False)
    for i, data in enumerate(validation_loader,0):
        # Every data instance is an input + label pair
        valid_input, valid_label = data
        # valid_input = valid_input.unsqueeze(dim=1).float()
        valid_label_one_hot= torch.tensor(to_categorical(y=valid_label, num_classes=num_classes)).float()
        if len(valid_label_one_hot.shape)==1:
          valid_label_one_hot = valid_label_one_hot.unsqueeze(dim=0)

        valid_input = valid_input.to(torch.device(train_device))
        valid_label = valid_label.to(torch.device(train_device))
        valid_label_one_hot = valid_label_one_hot.to(torch.device(train_device))

        # Make predictions for this batch
        valid_output, valid_decoded_input, valid_encoded_output = model(valid_input)
        valid_encoded_output = torch.reshape(valid_encoded_output, (valid_encoded_output.shape[0],-1))
        # print('valid_input:',valid_input.shape, 'valid_label:',valid_label.shape, 'valid_output:',valid_output.shape)

        # Gather data and report        
        valid_classifier_loss += loss_fn(valid_output, valid_label_one_hot).item()
        if loss_fn_type == 'contrastive':
          valid_encoder_loss += loss_fn2(valid_encoded_output, valid_label).item()
        else:
          valid_encoder_loss += loss_fn2(valid_input, valid_decoded_input).item()
        valid_loss = (lambda1)*valid_classifier_loss + (lambda2)*valid_encoder_loss
        for batch_count in range(valid_output.shape[0]):
          if(torch.argmax(valid_output[batch_count,:]) == torch.argmax(valid_label_one_hot[batch_count,:])):
            valid_correct += 1

    training_accuracy = 100*train_correct/num_training_samples
    validation_accuracy = 100*valid_correct/num_validation_samples

    return train_loss, train_encoder_loss, train_classifier_loss, training_accuracy, valid_loss, valid_encoder_loss, valid_classifier_loss, validation_accuracy

def train_epochs(X_train, y_train, X_test, y_test, 
                 model_parameters={'model_type': "Encoder+Classifier", 
                                   'model': None, 'num_filters': 8,
                                   'optimizer': None,
                                   'loss_fn_type': 'contrastive',
                                   'loss_fn': torch.nn.CrossEntropyLoss(), 
                                   'loss_fn2': torch.nn.MSELoss(), 
                                   'lambda1': 0.5, 'lambda2': 0.5},
                 max_state={'ntrails': 0, 'kfolds': 0, 'epochs': 1},
                 current_state={'trail': 0, 'fold': 0, 'epoch': 1},
                 best_state={'training_loss': 0, 'training_accuracy': 0, 
                               'validation_loss': 0,'validation_accuracy': 0, 
                               'trail': 0, 'fold': 0, 'epoch': 0},
                 transformation = True, auto_augmentation = True, 
                 early_stop_thresh=5, train_device='cuda', 
                 checkpoint_save_step=5,    
                 resume_from=None, results=[]):

  model = model_parameters['model']
  optimizer = model_parameters['optimizer']
  
  #resume
  if not resume_from == None:
      resume_checkpoint = torch.load(resume_from)
      current_state = resume_checkpoint['current_state']
      best_state = resume_checkpoint['best_validation_accuracy']
      best_validation_accuracy = best_state['validation_accuracy']
      results = resume_checkpoint['results']
      # load model and optimizer 
      model.load_state_dict(resume_checkpoint['model'])
      optimizer.load_state_dict(resume_checkpoint['optimizer'])

  trail = current_state['trail'] if resume_from == None else current_state['trail'] + 1
  fold = current_state['fold'] if resume_from == None else current_state['fold'] + 1
  epoch = current_state['epoch'] if resume_from == None else current_state['epoch'] + 1
  
  kfolds = max_state['kfolds']
  epochs = max_state['epochs']

  
  best_validation_accuracy = best_state['validation_accuracy']
  best_validation_index = (best_state['trail']-1)*kfolds*epochs + \
                     (best_state['fold']-1)*epochs + (best_state['epoch']-1)

  
  fold_best_validation_accuracy = 0
  fold_best_validation_accuracy_age = early_stop_thresh
  fold_best_validation_accuracy_epoch = 0

  #data
  # modification on November 5, 2023 for contrastive learning
  ear_images = np.concatenate((X_train, X_test))
  mean = np.mean(255*np.array(ear_images),axis=(0,2,3))
  std = np.std(255*np.array(ear_images),axis=(0,2,3))
  print('Atif')
  transform_train_images = []
  if transformation:
  	transform_train_images = [
      transforms.RandomCrop(128, padding=4),
      transforms.RandomHorizontalFlip(),
    ]
  if auto_augmentation:
  	transform_train_images.append(transforms.AutoAugment())
  
  transform_train_images = transforms.Compose(
    transform_train_images
  )
  
  transform_normalization = transforms.Compose(
    [
      transforms.Normalize(mean, std),
    ]
  )
  
  temp = transform_train_images(torch.tensor(255*X_train, dtype=torch.uint8))
  #print(f'X_train temp shape: {temp.shape}')
  transformed_X_train = transform_normalization(temp.to(dtype=torch.float32))
  training_loader = DataLoader(TensorDataset(transformed_X_train, torch.tensor(y_train)), batch_size=100, shuffle=True)
  
  # required because crop change train images dimenssion.
  transform_test_images = []
  if transformation:
  	transform_test_images = [
      transforms.RandomCrop(128, padding=4),
      transforms.RandomHorizontalFlip(),
    ]
    
  transform_test_images = transforms.Compose(
    transform_test_images
  )

  temp = transform_test_images(torch.tensor(255*X_test, dtype=torch.uint8))
  transformed_X_test = transform_normalization(temp.to(dtype=torch.float32))
  validation_loader = DataLoader(TensorDataset(transformed_X_test, torch.tensor(y_test)), batch_size=1)
  
  # training_loader = DataLoader(TensorDataset(torch.tensor(X_train), torch.tensor(y_train)), batch_size=100, shuffle=True)
  #validation_loader = DataLoader(TensorDataset(torch.tensor(X_test), torch.tensor(y_test)), batch_size=1)
  # added by Atif
  
  training_samples = training_loader.dataset.tensors[0]
  training_targets = training_loader.dataset.tensors[1]

  input_shape=(training_samples.shape[2], training_samples.shape[3], training_samples.shape[1])
  num_classes=np.unique(training_targets).shape[0]

  num_training_samples = len(training_loader.dataset)
  num_validation_samples = len(validation_loader.dataset)
  
  
  #print('Good Bye Atif')
  #sys.exit(0)
  #print(f'num_training_samples: {num_training_samples}\n num_validation_samples: {num_validation_samples}\n num_training_samples = {len(training_loader)}\n num_validation_samples = {len(validation_loader)}')
	
  # For Epochs results
  if trail== 0 and fold==0:
      results = [{'training_loss': 0, 'training_encoder_loss': 0, 
                  'training_classifier_loss': 0, 'training_accuracy': 0,
                  'validation_loss': 0, 'validation_encoder_loss': 0, 
                  'validation_classifier_loss': 0, 'validation_accuracy': 0, 
                  'current_state': {'trail': 0, 'fold': 0, 'epoch': 0}}]*epochs

  
  #print(f'\n checkpoint_save_step = {checkpoint_save_step}')
  for epoch in range(epoch, epochs+1):
    current_state = {'trail': trail, 'fold': fold, 'epoch': epoch}
    print('EPOCH {}/{}:'.format(epoch,epochs))
    # training_loss, training_accuracy, validation_loss, validation_accuracy 
    training_loss, training_encoder_loss, training_classifier_loss, training_accuracy, \
      validation_loss, validation_encoder_loss, validation_classifier_loss, validation_accuracy= \
      train_one_epoch(training_loader, validation_loader,
                      num_training_samples, num_validation_samples,
                      input_shape=input_shape, num_classes=num_classes,
                      model_parameters=model_parameters, train_device=train_device)

    current_index = (trail-1)*kfolds*epochs + (fold-1)*epochs + (epoch-1)
      # where train batch size is 100, 
    results[current_index] = {'training_loss': training_loss/(num_training_samples/100),
                              'training_encoder_loss': training_encoder_loss/(num_training_samples/100), 
                              'training_classifier_loss': training_classifier_loss/(num_training_samples/100),
                              'training_accuracy': training_accuracy, 
                              'validation_loss': validation_loss/num_validation_samples,
                              'validation_encoder_loss': validation_encoder_loss/num_validation_samples, 
                              'validation_classifier_loss': validation_classifier_loss/num_validation_samples,
                              'validation_accuracy': validation_accuracy,
                              'current_state': current_state}
    
    print(f"Training: \n Training Accuracy: {training_accuracy}%, Average Training Loss: {training_loss/len(training_loader)}")
    print(f"\n Average Training Encoder Loss: {training_encoder_loss/len(training_loader)}")
    print(f"\n Average Training Classifier Loss: {training_classifier_loss/len(training_loader)}")
    print(f"Validation: \n Validation Accuracy: {validation_accuracy}%, Average Validation Loss: {validation_loss/len(validation_loader)}")
    print(f"\n Average Validation Encoder Loss: {validation_encoder_loss/len(validation_loader)}")
    print(f"\n Average Validation Classifier Loss: {validation_classifier_loss/len(validation_loader)}")
      
    if validation_accuracy > best_validation_accuracy: 
        best_validation_accuracy = validation_accuracy 
        best_validation_index = current_index
        # Updating best state
        best_state = {'training_loss': training_loss/(num_training_samples/100), 
                      'training_encoder_loss': training_encoder_loss/(num_training_samples/100), 
                      'training_classifier_loss': training_classifier_loss/(num_training_samples/100), 
                      'training_accuracy': training_accuracy, 
                      'validation_loss': validation_loss/num_validation_samples, 
                      'validation_encoder_loss': validation_encoder_loss/num_validation_samples, 
                      'validation_classifier_loss': validation_classifier_loss/num_validation_samples, 
                      'validation_accuracy': validation_accuracy, 
                      'trail': trail, 'fold': fold, 'epoch': epoch}
        # creating the best checkpoint and saving it in the file
        best_checkpoint = { 
            'model': model.state_dict(), 
            'optimizer': optimizer.state_dict(),
            'training_loss': training_loss/(num_training_samples/100), 
            'training_encoder_loss': training_encoder_loss/(num_training_samples/100), 
            'training_classifier_loss': training_classifier_loss/(num_training_samples/100), 
            'training_accuracy': training_accuracy, 
            'validation_loss': validation_loss/num_validation_samples, 
            'validation_encoder_loss': validation_encoder_loss/num_validation_samples, 
            'validation_classifier_loss': validation_classifier_loss/num_validation_samples, 
            'validation_accuracy': validation_accuracy, 
            'current_state': current_state,
            'best_state': best_state,
            'max_state': max_state,
            'results': results,
        }
        torch.save(best_checkpoint, "best_checkpoint.pth")

    #torch.save(latest_checkpoint, "latest_checkpoint.pth")
    
    if validation_accuracy > fold_best_validation_accuracy:
        fold_best_validation_accuracy = validation_accuracy
        fold_best_validation_accuracy_age = 0
        print(f"fold_best_validation_accuracy {fold_best_validation_accuracy}")
    else:
        fold_best_validation_accuracy_age = fold_best_validation_accuracy_age+1
      
    if fold_best_validation_accuracy_age >= early_stop_thresh:
        print(f"early_stop_thresh {early_stop_thresh} {fold_best_validation_accuracy_age}")
        print(f"Early stopped training at state (trail, fold, epoch) = ({trail}, {fold}, {epoch})")
        print(f"The best vaidation accuarcy was {fold_best_validation_accuracy} at state (trail, fold, epoch) = ({trail}, {fold}, {epoch-early_stop_thresh})")
        for epoch in range(epoch+1, epochs+1):
            current_index = (trail-1)*kfolds*epochs + (fold-1)*epochs + (epoch-1)
            current_state = {'trail': trail, 'fold': fold, 'epoch': epoch}
            # where train batch size is 100, 
            results[current_index] = {'training_loss': training_loss/(num_training_samples/100),
                                      'training_encoder_loss': training_encoder_loss/(num_training_samples/100), 
                                      'training_classifier_loss': training_classifier_loss/(num_training_samples/100),
                                      'training_accuracy': training_accuracy, 
                                      'validation_loss': validation_loss/num_validation_samples,
                                      'validation_encoder_loss': validation_encoder_loss/num_validation_samples, 
                                      'validation_classifier_loss': validation_classifier_loss/num_validation_samples,
                                      'validation_accuracy': validation_accuracy,
                                      'current_state': current_state}
      
    print(f"After early stop {epoch}")
    # saving checkpoint after every "checkpoint_save_step" (default = 5)
    if (checkpoint_save_step > 0 and epoch%checkpoint_save_step==0) or (epoch >= epochs):
        # creating the latest checkpoint and saving it in the file
        latest_checkpoint = { 
                                'model': model.state_dict(), 
                                'optimizer': optimizer.state_dict(),
                                'training_loss': training_loss/(num_training_samples/100), 
                                'training_encoder_loss': training_encoder_loss/(num_training_samples/100), 
                                'training_classifier_loss': training_classifier_loss/(num_training_samples/100), 
                                'training_accuracy': training_accuracy, 
                                'validation_loss': validation_loss/num_validation_samples, 
                                'validation_encoder_loss': validation_encoder_loss/num_validation_samples, 
                                'validation_classifier_loss': validation_classifier_loss/num_validation_samples, 
                                'validation_accuracy': validation_accuracy, 
                                'current_state': current_state,
                                'best_state': best_state,
                                'max_state': max_state,
                                'results': results,
                            }
        torch.save(latest_checkpoint, "checkpoint_trail_" + str(trail) + "_fold_" + str(fold) + "_epoch_" + str(epoch) + ".pth")
    
    if fold_best_validation_accuracy_age >= early_stop_thresh:
        break;
    #if current_index - best_validation_index >= early_stop_thresh:
    #    print(f"Early stopped training at state (trail, fold, epoch) = ({trail}, {fold}, {epoch})")
    #    print(f"The best vaidation accuarcy was {best_state['validation_accuracy']} at state (trail, fold, epoch) = ({best_state['trail']}, {best_state['fold']}, {best_state['epoch']})")
    #    break  # terminate the training loop

  
  #print(f'Results of Trail {trail}, Fold {fold} and Epoch {epoch}: {results}')
  return results, best_state

def reset_weights(m):
  '''
    Try resetting model weights to avoid
    weight leakage.
  '''
  for layer in m.children():
   if hasattr(layer, 'reset_parameters'):
    #print(f'Reset trainable parameters of layer = {layer}')
    layer.reset_parameters()

def train_folds(ear_images, sub_labels, 
                model_parameters={'model_type': "Encoder+Classifier", 
                                  'model': None, 'num_filters': 8,
                                  'optimizer': None, 
                                  'loss_fn_type': 'contrastive', 
                                  'loss_fn': torch.nn.CrossEntropyLoss(), 
                                  'loss_fn2': torch.nn.MSELoss(), 
                                  'lambda1': 0.5, 'lambda2': 0.5},
                max_state={'ntrails': 0, 'kfolds': 0, 'epochs': 1},
                current_state={'trail': 0, 'fold': 1, 'epoch': 1},
                best_state={'training_loss': 0, 'training_accuracy': 0, 
                            'validation_loss': 0,'validation_accuracy': 0, 
                            'trail': 0, 'fold': 0, 'epoch': 0},
                transformation = True, auto_augmentation = True, 
                early_stop_thresh=5, train_device='cuda', 
                checkpoint_save_step=5, resume_from=None, results=[]):

    model = model_parameters['model']
    optimizer = model_parameters['optimizer']

    #best_validation_accuracy = best_state['validation_accuracy']
    #best_validation_index = (best_state['trail']-1)*k_folds*epochs_per_fold + \
    #  (best_state['fold']-1)*epochs_per_fold + (best_state['epoch']-1)
    
    #resume
    if not resume_from == None:
        resume_checkpoint = torch.load(resume_from)
        current_state = resume_checkpoint['current_state']
        best_state = resume_checkpoint['best_state']
        #max_state = resume_checkpoint['max_state']
        results = resume_checkpoint['results']
        # load model and optimizer 
        model.load_state_dict(resume_checkpoint['model'])
        optimizer.load_state_dict(resume_checkpoint['optimizer'])
    
    
    trail = current_state['trail'] if resume_from == None else current_state['trail'] + 1
    #fold = current_state['fold']
    #epoch = current_state['epoch']
    k_folds = max_state['kfolds']
    epochs_per_fold = max_state['epochs']
    
    # Set fixed random number seed
    kfold = StratifiedKFold(n_splits=k_folds, shuffle=True, random_state=42)
    
    # For k fold results
    if trail== 0:
        results = [{'training_loss': 0, 'training_accuracy': 0, 
                     'validation_loss': 0,'validation_accuracy': 0, 
                     'trail': 0, 'fold': 0, 'epoch': 0}]*(epochs_per_fold*k_folds)
        # results = np.zeros(k_folds)
    
    # Print k-fold results
    print(f'K-FOLD CROSS VALIDATION RESULTS FOR {k_folds} FOLDS')
    print('--------------------------------')
    #print(f'checkpoint_save_step = {checkpoint_save_step}')
    sum = 0.0
    # K-fold Cross Validation model evaluation
    for fold, (train_ids, test_ids) in enumerate(kfold.split(ear_images, sub_labels)):
        # Print
        print(f'FOLD {fold+1}')
        print('--------------------------------')
        X_train = ear_images[train_ids, :, :, :]
        y_train = sub_labels[train_ids]
        X_test = ear_images[test_ids, :, :, : ]
        y_test = sub_labels[test_ids]
                
        # Reset model weights before each fold
        model_checkpoint = torch.load("model_checkpoint.pth")
        model.load_state_dict(model_checkpoint['model'])
        optimizer.load_state_dict(model_checkpoint['optimizer'])
        # model.apply(reset_weights)
        
        current_state = {'trail': trail, 'fold': fold+1, 'epoch': 1}
        results, best_state = train_epochs(X_train, y_train, X_test, y_test, 
                                           model_parameters=model_parameters, 
                                           max_state=max_state, 
                                           current_state=current_state, 
                                           best_state=best_state, 
                                           transformation = transformation, 
                                           auto_augmentation = auto_augmentation,                                                          early_stop_thresh=early_stop_thresh, 
                                           train_device=train_device,
                                           checkpoint_save_step = checkpoint_save_step, 
                                           resume_from=resume_from, results=results)
        #best_validation_accuracy = best_state['validation_accuracy']
        st_ind = (trail-1)*k_folds*epochs_per_fold + fold*epochs_per_fold
        #print(f"\n Start Index: {st_ind}\n Trail: {trail} \n Fold: {fold} \n K Folds: {k_folds} \n Epochs per Fold: {epochs_per_fold}")
        temp = []
        for ind in range(st_ind, st_ind + epochs_per_fold):
            temp.append(results[ind]['validation_accuracy'])
        fold_best_validation_accuracy = max(temp)
        print(f'Fold {fold+1}: {fold_best_validation_accuracy} %')
        sum += fold_best_validation_accuracy
    
    k_folds_avg_validation_accuracy = sum/k_folds
    print(f'Average: {k_folds_avg_validation_accuracy} %')
    return k_folds_avg_validation_accuracy, best_state

def train_trails(ear_images, sub_labels,
                 model_parameters={'model_type': "Encoder+Classifier", 
                                   'model': None, 'num_filters': 8, 
                                   'optimizer': None, 
                                   'loss_fn_type': 'contrastive', 
                                   'loss_fn': torch.nn.CrossEntropyLoss(), 
                                   'loss_fn2': torch.nn.MSELoss(), 
                                   'lambda1': 0.5, 'lambda2': 0.5},
                 max_state={'ntrails': 0, 'kfolds': 0, 'epochs': 1},
                 current_state={'trail': 1, 'fold': 1, 'epoch': 1},
                 best_state={'training_loss': 0, 'training_accuracy': 0, 
                               'validation_loss': 0,'validation_accuracy': 0, 
                               'trail': 0, 'fold': 0, 'epoch': 0},
                 transformation = True, 
                 auto_augmentation = True,
                 early_stop_thresh=5, train_device='cuda', 
                 checkpoint_save_step=5, resume_from=None):

    model = model_parameters['model']
    optimizer = model_parameters['optimizer']
    
    #resume
    if not resume_from == None:
        resume_checkpoint = torch.load(resume_from)
        current_state = resume_checkpoint['current_state']
        best_state = resume_checkpoint['best_state']
        #max_state = resume_checkpoint['max_state']
        results = resume_checkpoint['results']
        #best_validation_accuracy = best_state['validation_accuracy'] 
        # load model and optimizer 
        model.load_state_dict(resume_checkpoint['model'])
        optimizer.load_state_dict(resume_checkpoint['optimizer'])
    
    trail = current_state['trail'] if resume_from == None else current_state['trail'] + 1
    #print(f'---Atif---trail:{trail}')                
    #fold = 1
    #epoch = 1
    #best_validation_accuracy = 0
    
    n_trails = max_state['ntrails']
    k_folds = max_state['kfolds']
    epochs_per_fold = max_state['epochs']
      
    # For N trail results
    results = [{'training_loss': 0, 'training_accuracy': 0, 
                'validation_loss': 0,'validation_accuracy': 0, 
                'trail': 0, 'fold': 0, 'epoch': 1}]*(epochs_per_fold*k_folds*n_trails)
    # results = np.zeros((n_trails, k_folds))

    # Print N trail results
    print(f'N-TRAILS CROSS VALIDATION RESULTS FOR {k_folds} FOLDS')
    print('--------------------------------')
    #print(f'checkpoint_save_step = {checkpoint_save_step}')
    sum = 0.0
    # N-trail Cross Validation model evaluation
    for trail in range(trail, n_trails+1):
        print(f"Trail: {trail}")
        #X, y = shuffle(ear_images, sub_labels, random_state=42)
        current_state = {'trail': trail, 'fold': 1, 'epoch': 1}
        k_folds_avg_validation_accuracy, best_state = train_folds(ear_images, sub_labels, model_parameters=model_parameters, max_state=max_state, current_state=current_state, best_state=best_state, transformation = transformation, auto_augmentation = auto_augmentation, early_stop_thresh=early_stop_thresh, train_device=train_device, checkpoint_save_step=checkpoint_save_step, resume_from=None, results=results)
        
        print(f'Trail {trail}: {k_folds_avg_validation_accuracy} %')
        sum += k_folds_avg_validation_accuracy
    
    print(f'Average: {sum/n_trails} %')
