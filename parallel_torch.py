# minimal torch example from https://github.com/jcjohnson/pytorch-examples#pytorch-nn
# adjusted to use DistributedDataParallel

import torch
import sys
import argparse
import torch.distributed as dist

class TwoLayerNet(torch.nn.Module):
  def __init__(self, D_in, H, D_out):
    """
    In the constructor we instantiate two nn.Linear modules and assign them as
    member variables.
    """
    super(TwoLayerNet, self).__init__()
    self.linear1 = torch.nn.Linear(D_in, H)
    self.linear2 = torch.nn.Linear(H, D_out)

  def forward(self, x):
    """
    In the forward function we accept a Tensor of input data and we must return
    a Tensor of output data. We can use Modules defined in the constructor as
    well as arbitrary (differentiable) operations on Tensors.
    """
    h_relu = self.linear1(x).clamp(min=0)
    y_pred = self.linear2(h_relu)
    return y_pred


def main(rank, master, worldsize):

  print('rank: ' + str(rank) + ", master: " + str(master) + ", worldsize: " + str(worldsize))

  use_cuda            = torch.cuda.is_available()
  device              = torch.device("cuda:0" if use_cuda else "cpu")

  print('device: ' + str(device))

  # network initialization
  dist.init_process_group(init_method='tcp://' + str(master), rank=rank, world_size=worldsize, backend="nccl")

  # N is batch size; D_in is input dimension;
  # H is hidden dimension; D_out is output dimension.
  N, D_in, H, D_out = 64, 1000, 100, 10

  # Create random Tensors to hold inputs and outputs
  x = torch.randn(N, D_in)
  y = torch.randn(N, D_out)

  # Construct our model by instantiating the class defined above.
  model = TwoLayerNet(D_in, H, D_out)
  model.to(device)

  model = torch.nn.parallel.DistributedDataParallel(model)
  x = x.cuda()
  y = y.cuda()

  # if you intend to use this, create a class implementing Dataset first
  # train_sampler = torch.utils.data.distributed.DistributedSampler(dataset,num_replicas=worldsize,rank=rank)

  # Construct our loss function and an Optimizer. The call to model.parameters()
  # in the SGD constructor will contain the learnable parameters of the two
  # nn.Linear modules which are members of the model.
  loss_fn = torch.nn.MSELoss(reduction='sum')
  optimizer = torch.optim.SGD(model.parameters(), lr=1e-4)
  for t in range(500):
    # Forward pass: Compute predicted y by passing x to the model
    y_pred = model(x)

    # Compute and print loss
    loss = loss_fn(y_pred, y)
    #print(t, loss.item())

    # Zero gradients, perform a backward pass, and update the weights.
    optimizer.zero_grad()
    loss.backward()
    optimizer.step()
  
  f = open("output.txt", "w")
  f.write(str(loss.item()))
  f.close()
  
if __name__ == "__main__":
  parser = argparse.ArgumentParser(description='Params')
  parser.add_argument('--rank')
  parser.add_argument('--master')
  parser.add_argument('--worldsize')
  args = parser.parse_args()
  main(rank=args.rank, master=args.master, worldsize=args.worldsize)
