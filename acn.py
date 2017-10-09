#coding:utf-8

import tensorflow as tf
import numpy as np


def conv(x, filter_height, filter_width, num_filters, stride_y, stride_x, name,
         padding='SAME', groups=1):
    # Get number of input channels
    input_channels = int(x.get_shape()[-1])

    # Create lambda function for the convolution
    convolve = lambda i, k: tf.nn.conv2d(i, k,
                                         strides=[1, stride_y, stride_x, 1],
                                         padding=padding)

    with tf.variable_scope(name) as scope:
        # Create tf variables for the weights and biases of the conv layer
        weights = tf.get_variable('weights',
                                  shape=[filter_height, filter_width,
                                         input_channels / groups, num_filters])
        biases = tf.get_variable('biases', shape=[num_filters])

        if groups == 1:
            conv = convolve(x, weights)

        # In the cases of multiple groups, split inputs & weights and
        else:
            # Split input and weights and convolve them separately
            input_groups = tf.split(x, groups, 3)
            weight_groups = tf.split(weights, groups, 3)
            output_groups = [convolve(i, k) for i, k in zip(input_groups, weight_groups)]

            # Concat the convolved output together again
            conv = tf.concat(axis = 3, values = output_groups)

        # Add biases
        # bias = tf.reshape(tf.nn.bias_add(conv, biases), conv.get_shape().as_list())
        bias = tf.nn.bias_add(conv, biases)

        # Apply relu function
        relu = tf.nn.relu(bias, name=scope.name)

        return relu


def fc(x, num_in, num_out, name, relu=True):
    with tf.variable_scope(name) as scope:

        # Create tf variables for the weights and biases
        weights = tf.get_variable('weights', shape=[num_in, num_out], trainable=True)
        biases = tf.get_variable('biases', [num_out], trainable=True)

        # Matrix multiply weights and inputs and add bias
        act = tf.nn.xw_plus_b(x, weights, biases, name=scope.name)

        if relu == True:
            # Apply ReLu non linearity
            relu = tf.nn.relu(act)
            return relu
        else:
            return act


def max_pool(x, filter_height, filter_width, stride_y, stride_x,
             name, padding='SAME'):
    return tf.nn.max_pool(x, ksize=[1, filter_height, filter_width, 1],
                          strides=[1, stride_y, stride_x, 1],
                          padding=padding, name=name)


def lrn(x, radius, alpha, beta, name, bias=1.0):
    return tf.nn.local_response_normalization(x, depth_radius=radius,
                                              alpha=alpha, beta=beta,
                                              bias=bias, name=name)


def dropout(x, keep_prob):
    return tf.nn.dropout(x, keep_prob)

# downsample conv5 from BxWxHxD to Bx13x13xD
def downsample(conv5):

    return conv5

# upsample Reweighting Mask m from Bx13x13x1 to BxWxHx1
def upsample(convw):

    return convw

class ACN(object):

    def __init__(self, x, skip_layer, keep_prob = 0, weights_path = 'DEFAULT'):

        """
        Inputs:
        :param x:
        :param keep_prob:
        :param skip_layer:
        :param weights_path:
        """

        # Parse input arguments
        self.X = x
        self.KEEP_PROB = keep_prob
        self.SKIP_LAYER = skip_layer
        if weights_path == 'DEFAULT':
            self.WEIGHTS_PATH = 'bvlc_alexnet.npy'
        else:
            self.WEIGHTS_PATH = weights_path

        # Call the create function to build the computational graph of AlexNet
        self.create()

    def create(self):

        # alexnet conv1 - conv5 that after Relu activation

        # 1st Layer: Conv (w ReLu) -> Lrn -> Pool
        conv1 = conv(self.X, 11, 11, 96, 4, 4, padding='VALID', name='conv1')
        norm1 = lrn(conv1, 2, 2e-05, 0.75, name='norm1')
        pool1 = max_pool(norm1, 3, 3, 2, 2, padding='VALID', name='pool1')

        # 2nd Layer: Conv (w ReLu) -> Lrn -> Poolwith 2 groups
        conv2 = conv(pool1, 5, 5, 256, 1, 1, groups=2, name='conv2')
        norm2 = lrn(conv2, 2, 2e-05, 0.75, name='norm2')
        pool2 = max_pool(norm2, 3, 3, 2, 2, padding='VALID', name='pool2')

        # 3rd Layer: Conv (w ReLu)
        conv3 = conv(pool2, 3, 3, 384, 1, 1, name='conv3')

        # 4th Layer: Conv (w ReLu) splitted into two groups
        conv4 = conv(conv3, 3, 3, 384, 1, 1, groups=2, name='conv4')

        # 5th Layer: Conv (w ReLu) -> Pool splitted into two groups
        conv5 = conv(conv4, 3, 3, 256, 1, 1, groups=2, name='conv5')


        # Contextual Reweighting Network
        conv5 = downsample(conv5)
        # g Multiscale Context Filters, dimension is Bx13x13x84
        convg3x3 = conv(conv5, 3, 3, 32, 1, 1, name='convg3x3')
        convg5x5 = conv(conv5, 5, 5, 32, 1, 1, name='convg5x5')
        convg7x7 = conv(conv5, 7, 7, 20, 1, 1, name='convg7x7')
        convg = tf.concat([convg3x3, convg5x5, convg7x7], -1)
        # w Accumulation Weight, 13x13x84 to 13x13x1
        convw = conv(convg, 1, 1, 1, 1, 1, name='convw')
        # 13x13x1 to WxHx1
        m = upsample(convw)


        # NetVLAD pooling layer, based on AlexNet

        # soft_assignment
        # x -> s, BxWxHxD is the dimension of conv5 output of AlexNet, and dimension of convs is BxWxHxK
        k_h = 1
        k_w = 1
        c_o = 64
        s_h = 1
        s_w = 1
        convs = conv(conv5, k_h, k_w, c_o, s_h, s_w, padding="SAME", name="convs")
        # s -> a
        conva = tf.nn.softmax(convs)
        # parameter ck, totally we have k cks.The dimension of ck is KxD.
        c = tf.Variable(tf.random_normal([256, 64]))  # 2-D python array

        # CRN on conva, BxWxHx1 on BxWxHxK

        # expand m from BxWxHx1 to BxWxHxK
        m_expand = tf.tile(m, [1, 1, 1, 64])
        conva = tf.multiply(m_expand, conva, name='m_conva')

        # VLAD core, get vector V whose dimension is K x D. Let's try to use a loop to assign V firstly.
        # a: reshape a from BxWxHxK to BxNxK
        conva_reshape = tf.reshape(conva, shape=[-1, 13 * 13, 64])
        # a: transpose a from NxK to KxNxB
        conva_transpose = tf.transpose(conva_reshape)
        # c: expand c from DxK to WxHxDxK
        c_expand = tf.tile(tf.expand_dims(tf.tile(tf.expand_dims(c, 0), [13, 1, 1]), 0), [13, 1, 1, 1])
        # c_batch = tf.tile(tf.expand_dims(c_expand, 0), [])
        # c:reshape c from WxHxDxK to NxDxK
        c_reshape = tf.reshape(c_expand, [169, 256, 64])
        # conv5: expand conv5 from BxWxHxD to BxWxHxDxK
        conv5_expand = tf.tile(tf.expand_dims(conv5, -1), [1, 1, 1, 1, 64])
        # conv5_reshape = tf.reshape(conv5, [13*13, 256])  #reshape conv5 from WxHxD to NxD
        # conv5: reshape conv5 from BxWxHxDxK to BxNxDxK
        conv5_reshape = tf.reshape(conv5_expand, [-1, 169, 256, 64])
        # residuals: dimension of residuals is BxNxDxK
        residuals = tf.subtract(conv5_reshape, c_reshape)
        # get V whose dimension is BxKxD
        # print(convs.get_shape()[0].value)
        for j in range(72):
            Vb = tf.Variable([])
            for i in range(64):
                if i == 0:
                    # V is calculated by 1xN multiply NxD, and dimension of V is 1xD
                    # conva_transpose is KxNxB, residuals is BxNxDxK
                    Vb = tf.matmul(
                        tf.reshape(
                            conva_transpose[i, :, j], [1, -1]), tf.reshape(residuals[j, :, :, i], [13 * 13, 256]))
                else:
                    Vb = tf.concat([Vb, tf.matmul(
                        tf.reshape(
                            conva_transpose[i, :, j], [1, -1]), tf.reshape(residuals[j, :, :, i], [13 * 13, 256]))], 0)
            if j == 0:
                V = tf.expand_dims(Vb, 0)
            else:
                V = tf.concat([V, tf.expand_dims(Vb, 0)], 0)

        # KxVxK = tf.matmul(conva_transpose, tf.subtract(conv5_reshape, c_expand))  # KxDxK
        # V = tf.Variable([], dtype='float32')
        # for i in range(64):
        #     V = tf.concat(0, [V, KxVxK[i, i]])  # KxD
        # V = tf.Variable(tf.zeros([64, 256]))
        # for k in range(64):
        #     for j in range(256):
        #         cc = tf.constant(-c[k][j])
        #         for w in range(13):
        #             for h in range(13):
        #                 V[k][j] = tf.assign(V[k][j],
        #                                     tf.add(tf.add(V[k][j], tf.multiply(conva[w][h][k], conv5[w][h][j])), cc))

        # intra-normalization
        V = tf.nn.l2_normalize(V, dim=2)

        # L2 normalization, output is a K x D discriptor
        V = tf.nn.l2_normalize(V, dim=1)

        # V: reshape V from BxKxD to Bx(KxD)
        self.output = tf.reshape(V, [72, -1])
        # print(output.get_shape())

    def load_initial_weights(self, session):

        # Load the weights into memory
        weights_dict = np.load(self.WEIGHTS_PATH, encoding='bytes').item()

        # Loop over all layer names stored in the weights dict
        for op_name in weights_dict:

            # Check if the layer is one of the layers that should be reinitialized
            if op_name not in self.SKIP_LAYER:

                if op_name in ['fc6', 'fc7', 'fc8']:
                    continue

                with tf.variable_scope(op_name, reuse=True):

                    # Loop over list of weights/biases and assign them to their corresponding tf variable
                    for data in weights_dict[op_name]:

                        # Biases
                        if len(data.shape) == 1:

                            var = tf.get_variable('biases', trainable=False)
                            session.run(var.assign(data))

                        # Weights
                        else:

                            var = tf.get_variable('weights', trainable=False)
                            session.run(var.assign(data))