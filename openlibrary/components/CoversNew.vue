<template>
    <div class="coversNew">
        <button type="button" @click="showModal = !showModal">Manage Covers</button>
        <div class="modal" :class="{hidden: !showModal}" :key="showModal">
            <div class="modal-content">
                <span class="close" @click="showModal = !showModal">&times;</span>
                <h1 class="center">Covers</h1>
                <a @click="showAdd = true" :class="{bold: showAdd}" href="javascript:;">Add</a> |
                <a @click="showAdd = false" :class="{bold: !showAdd}" href="javascript:;">Manage</a>
                <hr>

                <div :class="{hidden: !showAdd}">
                    <iframe :src="identifier + '/a/add-cover'"></iframe>
                </div>
                <div :class="{hidden: showAdd}">
                    <iframe :src="identifier + '/a/manage-covers'"></iframe>
                </div>
            </div>
        </div>
    </div>
</template>

<script>
export default {
    // Props are for external options; if a subelement of this is modified,
    // the view automatically re-renders
    props: {
        identifier: {
            type: String,
            default: () => 'default' // example: /works/OL45310W
        },
    },
    data: () => {
        return {
            showModal: false,
            showAdd: true,
        }
    },
    mounted() {
        window.addEventListener('message', this.receiveMessage)
    },
    methods: {
        receiveMessage(event) {
            if (event.data.message === 'closeCoverModal') this.showModal = false;
        }
    },
}
</script>
<!--
The css of the modal itself is from https://www.w3schools.com/howto/howto_css_modals.asp
We should decide which to keep and which to use from existing modal
-->
<style>
iframe {
    border: none;
    width: 580px;
    overflow-x: scroll !important;
    height: 450px;
}

.coversNew {
    display: flex;
    justify-content: center;
}

.hidden {
    display: none !important;
}

.modal {
    display: block; /* Hidden by default */
    position: fixed; /* Stay in place */
    z-index: 999999; /* Sit on top */
    left: 0;
    top: 0;
    width: 100%; /* Full width */
    height: 100%; /* Full height */
    overflow: auto; /* Enable scroll if needed */
    background-color: rgb(0, 0, 0); /* Fallback color */
    background-color: rgba(0, 0, 0, 0.4); /* Black w/ opacity */
}

/* Modal Content/Box */
.modal-content {
    background-color: #fefefe;
    margin: 5% auto; /* 15% from the top and centered */
    padding: 20px;
    border: 1px solid #888;
    width: 640px; /* set to this number to match the old covers modal */
}

/* The Close Button */
.close {
    color: #aaa;
    float: right;
    font-size: 28px;
    font-weight: bold;
}

.close:hover,
.close:focus {
    color: black;
    text-decoration: none;
    cursor: pointer;
}

.bold {
    font-weight: bold;
}

.center {
    text-align: center;
}
</style>
