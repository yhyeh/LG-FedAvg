LR=0.1
LE=1
EP=1000

#for RUN in cls_imb; do
for RUN in cls_imb; do

  # main_slct.py , adaptive gamma w.r.t. loss 
  for ALGO in 2 1 0; do
    for FRAC in 0.1 0.05; do
    
    
    # shard 10 fed w/ sel
    python3 main_slct.py --dataset cifar10 --model cnn --num_classes 10 --epochs ${EP} --lr ${LR} \
      --num_users 100 --shard_per_user 10 --frac ${FRAC} --local_ep ${LE} --local_bs 50 \
      --results_save cossim_${RUN} --myalgo ${ALGO} --gamma 1 --wndw_size 100 \
      --cls_imb --data_distr clsimb_dict_users.pkl
    
  
    # shard 2 fed w/ sel
    python3 main_slct.py --dataset cifar10 --model cnn --num_classes 10 --epochs ${EP} --lr ${LR} \
      --num_users 100 --shard_per_user 2 --frac ${FRAC} --local_ep ${LE} --local_bs 50 \
      --results_save cossim_${RUN} --myalgo ${ALGO} --gamma 1 --wndw_size 100 \
      --cls_imb --data_distr clsimb_dict_users.pkl


    done
  done
done

for RUN in cossim2; do

  # main_slct.py , adaptive gamma w.r.t. loss 
  for ALGO in 2; do
    for FRAC in 0.1 0.05; do
    
    
    # shard 10 fed w/ sel
    python3 main_slct.py --dataset cifar10 --model cnn --num_classes 10 --epochs ${EP} --lr ${LR} \
      --num_users 100 --shard_per_user 10 --frac ${FRAC} --local_ep ${LE} --local_bs 50 \
      --results_save ${RUN} --myalgo ${ALGO} --gamma 1 --wndw_size 100 \
      --data_distr unbalanced_dict_users_2.pkl
    
  
    # shard 2 fed w/ sel
    python3 main_slct.py --dataset cifar10 --model cnn --num_classes 10 --epochs ${EP} --lr ${LR} \
      --num_users 100 --shard_per_user 2 --frac ${FRAC} --local_ep ${LE} --local_bs 50 \
      --results_save ${RUN} --myalgo ${ALGO} --gamma 1 --wndw_size 100 \
      --data_distr unbalanced_dict_users_2.pkl


    done
  done
done