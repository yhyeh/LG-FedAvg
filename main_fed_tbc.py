#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Python version: 3.6

import copy
import pickle
import numpy as np
import pandas as pd
import torch
from torchinfo import summary

from utils.options import args_parser
from utils.train_utils import get_data, get_model
from utils.distribution import cosine_similarity
from models.Update import LocalUpdate
from models.test import test_img, DatasetByClass
import os

import pdb
import time
import datetime

if __name__ == '__main__':
    t_prog_bgin = time.time()
    # reproduce randomness
    torch.manual_seed(1001)
    np.random.seed(1001)
    # parse args
    args = args_parser()
    args.device = torch.device('cuda:{}'.format(args.gpu) if torch.cuda.is_available() and args.gpu != -1 else 'cpu')
    algo_dir = 'fedavg'
    base_dir = './save/{}/{}_iid{}_num{}_C{}_le{}/shard{}/{}/'.format(
        args.dataset, args.model, args.iid, args.num_users, args.frac, args.local_ep, args.shard_per_user, args.results_save)
    if not os.path.exists(os.path.join(base_dir, algo_dir)):
        os.makedirs(os.path.join(base_dir, algo_dir), exist_ok=True)
    
    #torch.manual_seed(int(time.time()))
    #np.random.seed(int(time.time()))
    dataset_train, dataset_test, dict_users_train, dict_users_test, distr_users, _ = get_data(args)
    '''
    print('type: ', type(dataset_test))
    print('len: ', len(dataset_test))
    local_data_size = []
    for idx in range(args.num_users):
        local_data_size.append(len(dict_users_train[idx]))
    print('local dataset size: ', local_data_size.sort())
    '''
    m = max(int(args.frac * args.num_users), 1) # num of selected clients
    
    distr_uni = np.ones(args.num_classes)
    distr_uni = distr_uni / np.linalg.norm(distr_uni)
    all_distr_glob_fraction = np.zeros((args.epochs, args.num_classes))
    distr_glob_frac_path = os.path.join(base_dir, algo_dir, 'distr_glob_frac.csv')
    distr_glob = np.zeros(args.num_classes) # normalized


    shard_path = './save/{}/data_distr/num{}/shard{}/'.format(
        args.dataset, args.num_users, args.shard_per_user)
    dict_save_path = os.path.join(shard_path, args.data_distr)
    if os.path.exists(dict_save_path): # use old one
        print('Local data already exist!')
        with open(dict_save_path, 'rb') as handle:
            (dict_users_train, dict_users_test, distr_users) = pickle.load(handle)
    else:
        print('Re dispatch data to local!')
        os.makedirs(shard_path, exist_ok=True)

        with open(dict_save_path, 'wb') as handle:
            pickle.dump((dict_users_train, dict_users_test, distr_users), handle)
            os.chmod(dict_save_path, 0o444) # read-only
    
    #torch.manual_seed(1001)
    #np.random.seed(1001)
    
    # build cloud model
    net_glob = get_model(args)
    
    # get model size
    glob_summary = summary(net_glob)
    #print(glob_summary)
    net_size = glob_summary.total_params

    net_glob.train()
    #print(list(net_glob.layer_hidden1.weight)[0])

    # training
    results_save_path = os.path.join(base_dir, algo_dir, 'results.csv')

    loss_train = []
    time_train = []
    net_best = None
    best_loss = None
    best_acc = None
    best_epoch = None

    lr = args.lr
    results = []

    cossim_glob_uni = np.zeros(args.epochs)
    cossim_glob_uni_path = os.path.join(base_dir, algo_dir, 'cossim_glob_uni.csv')
    acccls_save_path = os.path.join(base_dir, algo_dir, 'acc_test_by_cls.csv')
    losscls_save_path = os.path.join(base_dir, algo_dir, 'loss_test_by_cls.csv')
    all_acc_test_by_cls = np.zeros((args.epochs, args.num_classes))
    all_loss_test_by_cls = np.zeros((args.epochs, args.num_classes))
    
    ### simulate dynamic training + tx time
    time_simu = 0
    time_save_path= './save/user_config/var_time/{}_{}.csv'.format(args.dataset, args.num_users)
    if os.path.exists(time_save_path):
        # load shared config
        print('Load existed time config...')
        t_all = np.genfromtxt(time_save_path, delimiter=',')
    else:
        # generate new config and save
        print('Generate new time config...')
        t_all = np.zeros((args.num_users, args.epochs))
        t_mean = np.random.randint(1, 5, args.num_users) # rand choose from 1~10
        for u in range(args.num_users):
            t_all[u] = np.random.poisson(t_mean[u], size=args.epochs) + 1

    for iter in range(args.epochs):
        t_geps_bgin = time.time()
        #time_locals = []
        t_local = t_all[:, iter]
        
        w_glob = None
        loss_locals = []
        idxs_users = np.random.choice(range(args.num_users), m, replace=False)


        print("Round {}, lr: {:.6f}, {}".format(iter, lr, idxs_users))
        '''
        for idx in idxs_users:
            print('user: ', idx, '==================================')
            print('dict_users_train[idx]: ', type(dict_users_train[idx]), len(dict_users_train[idx]))
            #print(dict_users_train[idx])
        '''
        
        for idx in idxs_users: # iter over selected clients
            t_leps_bgin = time.time()

            local = LocalUpdate(args=args, dataset=dataset_train, idxs=dict_users_train[idx])
            net_local = copy.deepcopy(net_glob)

            w_local, loss = local.train(net=net_local.to(args.device), lr=lr)
            loss_locals.append(copy.deepcopy(loss))
            # loss: a float, avg loss over local epochs over batches
            #print('loss: ', loss)

            # calculate global data distribution
            distr_glob += distr_users[idx]
            distr_glob_fraction = distr_glob / sum(distr_glob)
            all_distr_glob_fraction[iter] = distr_glob_fraction
            #distr_glob = distr_glob / sum(distr_glob) # indicate the portion of label
            #distr_glob = distr_glob / np.linalg.norm(distr_glob)


            if w_glob is None:
                w_glob = copy.deepcopy(w_local)
            else:
                for k in w_glob.keys(): # layer by layer
                    w_glob[k] += w_local[k]
            
            t_leps_end = time.time()
            #time_locals.append(t_leps_end - t_leps_bgin)
            #time_locals.append(t_local[idx])

        lr *= args.lr_decay # default: no decay

        # update global weights
        for k in w_glob.keys():
            w_glob[k] = torch.div(w_glob[k], m) # calculate avg by dividing m

        # copy weight to net_glob
        net_glob.load_state_dict(w_glob)

        # print loss
        loss_avg = sum(loss_locals) / len(loss_locals)
        #loss_train.append(loss_avg)
        
        cossim_glob_uni[iter] = cosine_similarity(distr_glob, distr_uni)

        print('global distribution after round {}(%): {}'.format(iter, [format(100*x, '3.2f') for x in distr_glob_fraction]))
        print('cossim(global, uniform): ', cossim_glob_uni[iter])
        
        t_geps_end = time.time() # not include validation time
        time_glob = t_geps_end - t_geps_bgin
        time_train.append(time_glob)
        #time_local_avg = sum(time_locals) / len(time_locals)
        time_local_max = max(t_local[idxs_users])
        time_simu += time_local_max

        if (iter + 1) % args.test_freq == 0:
            net_glob.eval()
            acc_test, loss_test = test_img(net_glob, dataset_test, args)
            print('Round {:3d}, Average loss {:.3f}, Test loss {:.3f}, Test accuracy: {:.2f}, Max local runtime: {:.2f}, Simu runtime: {:.2f}, global runtime: {:.2f}'.format(
                iter, loss_avg, loss_test, acc_test, time_local_max, time_simu, time_glob))
            
            # test by class
            #acc_test_by_cls = np.zeros(args.num_classes)
            #loss_test_by_cls = np.zeros(args.num_classes)
            for cls in range(args.num_classes):
                all_acc_test_by_cls[iter][cls], all_loss_test_by_cls[iter][cls] = test_img(net_glob, DatasetByClass(dataset_test, cls), args)
            
            print('acc_test_by_cls:', all_acc_test_by_cls[iter])

            
            print(base_dir, algo_dir)

            if best_acc is None or acc_test > best_acc:
                net_best = copy.deepcopy(net_glob)
                best_acc = acc_test
                best_epoch = iter

            # if (iter + 1) > args.start_saving:
            #     model_save_path = os.path.join(base_dir, algo_dir, 'model_{}.pt'.format(iter + 1))
            #     torch.save(net_glob.state_dict(), model_save_path)

            results.append(np.array([iter, loss_avg, loss_test, acc_test, best_acc, 
                                     time_local_max, time_simu, time_glob, idxs_users.tolist()]))
            final_results = np.array(results)
            final_results = pd.DataFrame(final_results, columns=['epoch', 'loss_avg', 'loss_test', 'acc_test', 
                            'best_acc', 'time_local_max', 'time_simu', 'time_glob', 'user_explor'])
            final_results.to_csv(results_save_path, index=False)
        '''
        if (iter + 1) % 50 == 0:
            best_save_path = os.path.join(base_dir, algo_dir, 'best_{}.pt'.format(iter + 1))
            model_save_path = os.path.join(base_dir, algo_dir, 'model_{}.pt'.format(iter + 1))
            torch.save(net_best.state_dict(), best_save_path)
            torch.save(net_glob.state_dict(), model_save_path)
        '''
    np.savetxt(time_save_path, t_all, delimiter=",")
    np.savetxt(cossim_glob_uni_path, cossim_glob_uni, delimiter=",")
    np.savetxt(distr_glob_frac_path, all_distr_glob_fraction, delimiter=",")
    np.savetxt(acccls_save_path, all_acc_test_by_cls, delimiter=",")
    np.savetxt(losscls_save_path, all_loss_test_by_cls, delimiter=",")

    t_prog = time.time() - t_prog_bgin
    print('Best model, iter: {}, acc: {}'.format(best_epoch, best_acc))
    print('Program execution time:', datetime.timedelta(seconds=t_prog))