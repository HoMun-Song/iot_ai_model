from glob import glob
from tqdm import tqdm
from time import time
import logging
import os

import torch
import torch.optim as optim
import torch.nn as nn
from torch.utils.data import random_split

from model import Unet
from dataset import ImageDataset

BATCH_SIZE = 16
EPOCHS = 1000
LR = 0.0001

checkpoints_path = 'check_points/unet'
data_path = 'dataset/supervisely_person'

paths = glob(os.path.join(data_path,"**/*.png"))

logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(message)s')
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)


def get_random_data(dataset):
    id = np.random.randint(len(dataset))
    path, image, mask = dataset[id]
    return image, mask


def convert_tensor_to_img(tensor):
    img = tensor.cpu().detach().numpy()
    img = np.transpose(img, (1,2,0))
    return img
    
    
def convert_img_to_tensor(img, device = 'cpu'):
    return torch.tensor(img.reshape(1,3,256,256)).to(device)


def show_image(image, alpha=1, title=None):
    plt.imshow(image, alpha=alpha)
    plt.title(title)
    plt.axis('off')
    
    
def show_predictions(epoch, model, dataset, n_images=1, dispaly= True, save= True):
    for i in range(n_images):
        plt.figure(figsize=(10,8))
        
        img, mask = get_random_data(dataset)
        tensor = convert_img_to_tensor(img, device= device)
        pred_mask = model(tensor)
        
        plt.subplot(1,3,1)
        img = np.transpose(img, (1,2,0))
        show_image(img, title='Original Image')
        
        plt.subplot(1,3,2)
        mask = np.transpose(mask, (1,2,0))
        show_image(mask, title='Original Mask')
        
        plt.subplot(1,3,3)
        pred_img = convert_tensor_to_img(pred_mask[0])
        show_image(pred_img, title='Predicted Mask')
        
        if dispaly:
            plt.show()
        
        if save:
            plt.savefig(os.path.join(checkpoints_path, 'val', f'{epoch}.jpg'))


def fit(model, dataloader, criterion, optimizer, device, half = False):
    loss = .0
    acc = .0
    correct = 0
    start_time = time()
    
    progress = tqdm(dataloader)
    for path, data, target in progress:
        data = data.to(device).type(torch.float32)
        target = target.to(device).type(torch.float32)
        
        if half :
            data = data.half()
        
        output = model(data)
        output = output.squeeze(dim=1)
        loss = criterion(output, target)
        
        if model.training:
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            
        loss += loss
        
        output[output >= 0.5] = 1
        output[output < 0.5] = 0
        correct += output.eq(target).int().sum()

    acc = (correct/len(dataloader.dataset))
    loss = loss/len(dataloader.dataset)
    logger.info("{}, duration:{:6.1f}s, acc:{:.4f}, loss:{:.4f}".format(('trn' if model.training else 'val'), 
                                                                         time()-start_time, 
                                                                         acc, 
                                                                         loss ))
    return float(loss), float(acc)


if __name__ == '__main__':
    dataset = ImageDataset(data_path)
    
    dataset_size = len(dataset)
    trn_size = int(dataset_size * 0.8)
    val_size = dataset_size - trn_size
    trn_ds, val_ds = random_split(dataset, [trn_size, val_size])
    trn_loader = torch.utils.data.DataLoader(trn_ds, batch_size= BATCH_SIZE, shuffle=True)
    val_loader = torch.utils.data.DataLoader(val_ds, batch_size= BATCH_SIZE, shuffle=False)
    logger.info(f'trn: {len(trn_ds)}, val: {len(val_ds)}')    
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f'Load on {device}')
    
    model = Unet().to(device)
    params_cnt = sum(p.numel() for p in model.parameters() if p.requires_grad)
    logger.info(f'loaded model (params {params_cnt})')
    
    criterion = nn.BCELoss()
    optimizer = optim.Adam(model.parameters(), lr = LR)
    
    
    trn_loss = []
    trn_acc = []
    val_loss = []
    val_acc = []

    half = False

    min_loss = 99999.
    early_count = 0
    for epoch in range(1, EPOCHS+1):
        logger.info(f'epoch {epoch}')

        model.train()
        loss, acc = fit(model, trn_loader, criterion, optimizer, device, half=half)

        trn_loss.append(loss)
        trn_acc.append(acc)

        model.eval()
        with torch.no_grad():
            loss, acc = fit(model, val_loader, criterion, optimizer, device, half=half)

            # if loss >= min_loss:
            #     early_count += 1
            #     if early_count >= early_stopping:
            #         break
            # else:
            #     min_loss = loss
            #     early_count = 0

            if len(val_loss) > 0 and min(val_loss) > loss:
                torch.save(model.state_dict(), f"{checkpoints_path}/model_state_dict_{epoch}_best.pt")

            val_loss.append(loss)

        show_predictions(epoch, model, val_ds)

    torch.save(model.state_dict(), f"{checkpoints_path}/model_state_dict_{epoch}.pt")