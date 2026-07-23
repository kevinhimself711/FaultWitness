using System;
using System.IO;

namespace FaultWitness.Bootstrap
{
    internal static class SshAskpass
    {
        private static int Main()
        {
            string secret = Environment.GetEnvironmentVariable("FW_SSH_PASSWORD");
            if (String.IsNullOrEmpty(secret))
            {
                return 2;
            }

            string sentinel = Environment.GetEnvironmentVariable("FW_SSH_ASKPASS_SENTINEL");
            if (!String.IsNullOrEmpty(sentinel))
            {
                File.WriteAllText(sentinel, "invoked");
            }

            Console.Out.Write(secret);
            return 0;
        }
    }
}
